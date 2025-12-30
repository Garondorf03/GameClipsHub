from flask import Flask, render_template, request, jsonify
from azure.storage.blob import BlobServiceClient
from azure.cosmos import CosmosClient
import os
import json
from datetime import datetime
from dotenv import load_dotenv
from flask import Response
import io

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


@app.route('/api/images', methods=['GET'])
def list_images():
    try:
        items = []

        # If Cosmos DB is configured, return items from the metadata store
        if cosmos_container:
            query = (
                "SELECT c.fileName, c.userID, c.userName, c.blobUrl, c.blobPath, c.timestamp, c.contentType "
                "FROM c ORDER BY c.timestamp DESC"
            )
            for it in cosmos_container.query_items(query=query, enable_cross_partition_query=True):
                items.append(it)

        # Otherwise, list blobs directly from the storage container
        elif blob_service_client:
            container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
            for blob in container_client.list_blobs():
                blob_name = getattr(blob, 'name', None)
                try:
                    blob_client = container_client.get_blob_client(blob_name)
                    blob_url = blob_client.url
                except Exception:
                    blob_url = None

                content_type = ''
                try:
                    content_type = blob.content_settings.content_type if getattr(blob, 'content_settings', None) else ''
                except Exception:
                    content_type = ''

                items.append({
                    'fileName': os.path.basename(blob_name) if blob_name else '',
                    'blobUrl': blob_url,
                    'blobPath': blob_name,
                    'timestamp': blob.last_modified.isoformat() if getattr(blob, 'last_modified', None) else None,
                    'contentType': content_type,
                })

        return jsonify(items), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/blob', methods=['GET'])
def proxy_blob():
    """Stream a blob through the Flask server. Query param: path=container/path/to/blob or just blob/path (container fixed)."""
    path = request.args.get('path') or request.args.get('blobPath')
    if not path:
        return jsonify({'error': 'missing path parameter'}), 400

    if not blob_service_client:
        return jsonify({'error': 'Blob storage not configured'}), 500

    try:
        container_client = blob_service_client.get_container_client(BLOB_CONTAINER_NAME)
        # normalize: if path includes container name prefix, strip it
        blob_name = path
        # if user passed full URL, try to extract the blob path
        if path.startswith('http'):
            # naive extraction: take everything after the container name
            try:
                from urllib.parse import urlparse
                p = urlparse(path)
                # path like /container/blob/path
                parts = p.path.split('/')
                if len(parts) >= 3:
                    # parts[1] is container name
                    blob_name = '/'.join(parts[2:])
            except Exception:
                pass

        blob_client = container_client.get_blob_client(blob_name)
        downloader = blob_client.download_blob()
        data = downloader.readall()
        # attempt to get content type
        content_type = ''
        try:
            props = blob_client.get_blob_properties()
            content_type = getattr(props.content_settings, 'content_type', '') or ''
        except Exception:
            content_type = ''

        if not content_type:
            content_type = 'application/octet-stream'

        return Response(data, mimetype=content_type)

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
