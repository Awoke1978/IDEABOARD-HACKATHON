from flask import Flask, render_template, request, redirect, url_for, send_file
import psycopg2
import psycopg2.extras
from io import BytesIO
from PIL import Image, ExifTags

app = Flask(__name__)

# Database connection parameters
DATABASE_NAME = "attendance_db"
USER_NAME = "postgres"
PASSWORD = "dakshin"
HOST = "localhost"
PORT = "5432"

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
        # Open the image file
        image = Image.open(image_path)
        exif_data = image._getexif()

        if not exif_data:
            print("No EXIF data found.")
            return None

        gps_info = {}
        for tag, value in exif_data.items():
            tag_name = ExifTags.TAGS.get(tag, tag)
            if tag_name == "GPSInfo":
                gps_info = value
                break

        if not gps_info:
            print("No GPS info found in EXIF data.")
            return None

        def convert_to_degrees(value):
            """Helper function to convert GPS coordinates to decimal degrees."""
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

            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                cursor.execute(
                    'INSERT INTO guard_attendance (image, guard_name, latitude, longitude) VALUES (%s, %s, %s, %s)',
                    (img_byte_arr, guard_name, latitude, longitude)
                )
                conn.commit()
                return redirect(url_for('upload'))
            except Exception as e:
                print(f"Error saving image: {e}")
            finally:
                cursor.close()
                conn.close()

    return render_template('upload.html')

@app.route('/admin', methods=['GET'])
def admin():
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cursor.execute('SELECT * FROM guard_attendance')
        records = cursor.fetchall()
        
        cursor.execute('SELECT MAX(timestamp) AS last_timestamp FROM guard_attendance')
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
