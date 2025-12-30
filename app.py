from flask import Flask, render_template, request, jsonify
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient
import os
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')

# Azure configuration
BLOB_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
COSMOS_CONNECTION_STRING = os.getenv("COSMOS_CONNECTION_STRING")
BLOB_CONTAINER_NAME = "images"
COSMOS_DATABASE_ID = "MediaDB"
COSMOS_CONTAINER_ID = "Assets"

# Initialize clients (only if credentials are available)
blob_service_client = None
cosmos_container = None

if BLOB_CONNECTION_STRING:
    blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)

if COSMOS_CONNECTION_STRING:
    cosmos_client = CosmosClient.from_connection_string(COSMOS_CONNECTION_STRING)
    cosmos_container = cosmos_client.get_database_client(COSMOS_DATABASE_ID).get_container_client(COSMOS_CONTAINER_ID)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/upload', methods=['POST'])
def upload_file():
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        file_name = request.form.get('fileName', 'untitled')
        user_id = request.form.get('userID', 'unknown')
        user_name = request.form.get('userName', 'anonymous')
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not blob_service_client:
            return jsonify({'error': 'Blob storage not configured'}), 500
        
        # Generate blob filename
        timestamp = datetime.utcnow().isoformat()
        blob_filename = f"{user_id}/{timestamp}_{file.filename}"
        
        # Upload to blob storage
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        blob_client = container_client.get_blob_client(blob_filename)
        blob_client.upload_blob(file.stream, overwrite=True)
        
        blob_url = blob_client.url
        
        # Save metadata to Cosmos DB if configured
        if cosmos_container:
            metadata = {
                'id': blob_filename.replace('/', '_'),
                'fileName': file_name,
                'userID': user_id,
                'userName': user_name,
                'blobUrl': blob_url,
                'blobPath': blob_filename,
                'timestamp': timestamp,
                'contentType': file.content_type
            }
            cosmos_container.create_item(body=metadata)
        
        return jsonify({
            'success': True,
            'message': 'File uploaded successfully',
            'blobUrl': blob_url,
            'fileName': blob_filename
        }), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
