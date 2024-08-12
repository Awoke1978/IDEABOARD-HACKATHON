from flask import Flask, render_template, request, redirect, url_for, send_file
import psycopg2
import psycopg2.extras
from io import BytesIO
from PIL import Image, ExifTags
from datetime import datetime
from shapely.geometry import Point, Polygon

app = Flask(__name__)

# Database connection parameters
DATABASE_NAME = "attendance_db"
USER_NAME = "postgres"
PASSWORD = "dakshin"
HOST = "localhost"
PORT = "5432"

# Define the geographical boundary of Chennai (example coordinates, should be more accurate)
chennai_polygon_coords = [
    (80.00318186871408, 13.351066789714721),
    (80.00318186871408, 12.86828560130985),
    (80.5085899702865, 12.86828560130985),
    (80.5085899702865, 13.351066789714721),
    (80.00318186871408, 13.351066789714721)   # Close the polygon by repeating the first point
]

def get_db_connection():
    conn = psycopg2.connect(
        database=DATABASE_NAME,
        user=USER_NAME,
        password=PASSWORD,
        host=HOST,
        port=PORT
    )
    return conn

def get_geotagging(image_path):
    try:
        image = Image.open(image_path)
        exif_data = image._getexif()
        if not exif_data:
            return None

        gps_info = {}
        for tag, value in exif_data.items():
            tag_name = ExifTags.TAGS.get(tag, tag)
            if tag_name == "GPSInfo":
                gps_info = value
                break

        if not gps_info:
            return None

        def convert_to_degrees(value):
            d, m, s = value
            return d + (m / 60.0) + (s / 3600.0)

        latitude = convert_to_degrees(gps_info.get(2, (0, 0, 0)))
        if gps_info.get(3) == 'S':
            latitude = -latitude

        longitude = convert_to_degrees(gps_info.get(4, (0, 0, 0)))
        if gps_info.get(1) == 'W':
            longitude = -longitude

        return latitude, longitude

    except Exception as e:
        print(f"Error occurred: {e}")
        return None

def is_within_polygon(lat, lon, polygon_coords):
    point = Point(lon, lat)  # Shapely uses (lon, lat) for coordinates
    polygon = Polygon(polygon_coords)
    return polygon.contains(point)

@app.route('/')
def index():
    return redirect(url_for('upload'))

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        guard_name = request.form['guard_name']
        image_file = request.files['image']

        if image_file and guard_name:
            img_byte_arr = BytesIO()
            image_file.save(img_byte_arr)
            img_byte_arr = img_byte_arr.getvalue()

            temp_image_path = 'temp_image.jpg'
            with open(temp_image_path, 'wb') as f:
                f.write(img_byte_arr)

            coordinates = get_geotagging(temp_image_path)
            if coordinates:
                latitude, longitude = coordinates
            else:
                latitude, longitude = None, None

            # Check if coordinates fall within Chennai
            if latitude and longitude and is_within_polygon(latitude, longitude, chennai_polygon_coords):
                conn = get_db_connection()
                cursor = conn.cursor()

                try:
                    # Check if a record with the same guard_name exists and has no end timestamp
                    cursor.execute(
                        'SELECT id, start_timestamp, end_timestamp FROM guard_attendance WHERE guard_name = %s AND end_timestamp IS NULL',
                        (guard_name,)
                    )
                    existing_record = cursor.fetchone()

                    if existing_record:
                        # Update the end timestamp of the existing record
                        record_id, start_timestamp, _ = existing_record
                        cursor.execute(
                            'UPDATE guard_attendance SET end_timestamp = %s WHERE id = %s',
                            (datetime.now(), record_id)
                        )
                    else:
                        # Insert a new record with the start timestamp
                        cursor.execute(
                            'INSERT INTO guard_attendance (image, guard_name, latitude, longitude, start_timestamp) VALUES (%s, %s, %s, %s, %s)',
                            (img_byte_arr, guard_name, latitude, longitude, datetime.now())
                        )
                    
                    conn.commit()
                    return redirect(url_for('upload'))
                except Exception as e:
                    print(f"Error saving image: {e}")
                finally:
                    cursor.close()
                    conn.close()
            else:
                print("Coordinates are outside Chennai. Record rejected.")
                return "Coordinates are outside Chennai. Record rejected."

    return render_template('upload.html')

@app.route('/admin', methods=['GET'])
def admin():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cursor.execute('SELECT * FROM guard_attendance')
        records = cursor.fetchall()
        
        # Debugging: print records to console
        print("Admin records fetched:")
        for record in records:
            print(record)
        
        cursor.execute('SELECT MAX(start_timestamp) AS last_timestamp FROM guard_attendance')
        last_timestamp = cursor.fetchone()['last_timestamp']
    except Exception as e:
        print(f"Error fetching data: {e}")
        records = []
        last_timestamp = None
    finally:
        cursor.close()
        conn.close()
    
    return render_template('admin.html', records=records, last_timestamp=last_timestamp)

@app.route('/image/<int:image_id>')
def image(image_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('SELECT image FROM guard_attendance WHERE id = %s', (image_id,))
        image_data = cursor.fetchone()[0]
        return send_file(BytesIO(image_data), mimetype='image/jpeg')
    except Exception as e:
        print(f"Error fetching image: {e}")
        return "Error fetching image", 500
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)
