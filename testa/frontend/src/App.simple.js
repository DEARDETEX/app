import React, { useState } from 'react';
import axios from 'axios';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
    const [selectedFile, setSelectedFile] = useState(null);
    const [uploadStatus, setUploadStatus] = useState('');

    const handleFileSelect = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setSelectedFile(file);
        setUploadStatus('Uploading...');

        try {
            const formData = new FormData();
            formData.append('file', file);

            console.log('🚀 Uploading file:', file.name);
            
            const response = await axios.post(`${API}/upload-model`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            console.log('✅ Upload successful:', response.data);
            setUploadStatus(`✅ Uploaded successfully! Model ID: ${response.data.id}`);
            
        } catch (error) {
            console.error('❌ Upload failed:', error);
            setUploadStatus(`❌ Upload failed: ${error.response?.data?.detail || error.message}`);
        }
    };

    return (
        <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
            <h1>🚀 HoloForge - 3D Model Upload Test</h1>
            
            <div style={{ border: '2px dashed #ccc', padding: '20px', margin: '20px 0' }}>
                <input 
                    type="file" 
                    accept=".obj,.fbx,.gltf,.glb,.ply"
                    onChange={handleFileSelect}
                />
                <p>Select a 3D model file to upload</p>
            </div>

            {selectedFile && (
                <div style={{ margin: '20px 0' }}>
                    <p><strong>Selected file:</strong> {selectedFile.name}</p>
                    <p><strong>Size:</strong> {(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>
                </div>
            )}

            {uploadStatus && (
                <div style={{ 
                    padding: '10px', 
                    backgroundColor: uploadStatus.includes('❌') ? '#ffe6e6' : '#e6ffe6',
                    border: `1px solid ${uploadStatus.includes('❌') ? '#ff0000' : '#00ff00'}`,
                    margin: '20px 0'
                }}>
                    <p>{uploadStatus}</p>
                </div>
            )}

            <div style={{ margin: '20px 0', padding: '20px', backgroundColor: '#f0f0f0' }}>
                <h2>🔧 Debug Info</h2>
                <p><strong>Backend URL:</strong> {BACKEND_URL}</p>
                <p><strong>API Endpoint:</strong> {API}</p>
            </div>
        </div>
    );
}

export default App;