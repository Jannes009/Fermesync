from flask import Blueprint, render_template, request, redirect, url_for, flash
from db import create_db_connection, close_db_connection
import base64

document_bp = Blueprint('document', __name__)

@document_bp.route('/upload_document', methods=['GET', 'POST'])
def upload_document():
    if request.method == 'POST':
        del_note_no = request.form.get('del_note_no')
        image_data = request.form.get('image_data')

        if not del_note_no or not image_data:
            return redirect(url_for('document.upload_document'))

        # Remove header from base64 string
        if ',' in image_data:
            image_data = image_data.split(',')[1]

        # Decode the image data
        image_blob = base64.b64decode(image_data)

        conn = create_db_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO ZZDeliveryDocuments (DelNoteNo, Document)
                VALUES (?, ?)
            """, (del_note_no, image_blob))
            conn.commit()
        except Exception as e:
            conn.rollback()
            flash(f"Error saving document: {str(e)}")
        finally:
            close_db_connection(cursor, conn)

        return redirect(url_for('photo.upload_document'))

    return render_template('Add Document/index.html')
