import React, { useState } from 'react';
import axios from 'axios';
import ModelViewer from './components/ModelViewer';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
    const [selectedFile, setSelectedFile] = useState(null);
    const [modelUrl, setModelUrl] = useState(null);
    const [uploadStatus, setUploadStatus] = useState('');
    const [showTestCube, setShowTestCube] = useState(true);
    const [show3DViewer, setShow3DViewer] = useState(false);

    const handleFileSelect = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setSelectedFile(file);
        setUploadStatus('Uploading...');

        try {
            const formData = new FormData();
            formData.append('file', file);

            console.log('🚀 [App] Uploading file:', file.name);
            
            const response = await axios.post(`${API}/upload-model`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                }
            });

            console.log('✅ [App] Upload successful:', response.data);
            
            // Construct the model URL
            const fileUrl = `${BACKEND_URL}/api/${response.data.file_path}`;
            console.log('🎯 [App] Model URL:', fileUrl);
            
            setModelUrl(fileUrl);
            setShowTestCube(false);
            setShow3DViewer(true);
            setUploadStatus(`✅ Uploaded successfully! Loading 3D model...`);
            
        } catch (error) {
            console.error('❌ [App] Upload failed:', error);
            setUploadStatus(`❌ Upload failed: ${error.response?.data?.detail || error.message}`);
        }
    };

    const handleToggleTestCube = () => {
        setShowTestCube(!showTestCube);
        setShow3DViewer(true);
    };

    const handleToggle3DViewer = () => {
        setShow3DViewer(!show3DViewer);
    };

    return (
        <div style={{ 
            width: '100vw', 
            height: '100vh', 
            backgroundColor: '#222',
            color: 'white',
            fontFamily: 'Arial, sans-serif',
            display: 'flex',
            flexDirection: 'column'
        }}>
            {/* Header Controls */}
            <div style={{ 
                padding: '20px',
                backgroundColor: 'rgba(0,0,0,0.8)',
                borderBottom: '2px solid #444'
            }}>
                <h1 style={{ color: '#00ffff', margin: '0 0 20px 0' }}>
                    🚀 HoloForge - 3D Model Viewer
                </h1>
                
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '10px' }}>
                    <input 
                        type="file" 
                        accept=".obj,.fbx,.gltf,.glb,.ply"
                        onChange={handleFileSelect}
                        style={{ color: 'white' }}
                    />
                    
                    <button 
                        onClick={handleToggleTestCube}
                        style={{
                            padding: '8px 16px',
                            backgroundColor: showTestCube ? '#ff4444' : '#0088ff',
                            color: 'white',
                            border: 'none',
                            cursor: 'pointer',
                            borderRadius: '4px'
                        }}
                    >
                        {showTestCube ? 'Hide Test Cube' : 'Show Test Cube'}
                    </button>
                    
                    <button 
                        onClick={handleToggle3DViewer}
                        style={{
                            padding: '8px 16px',
                            backgroundColor: show3DViewer ? '#44ff44' : '#666666',
                            color: 'white',
                            border: 'none',
                            cursor: 'pointer',
                            borderRadius: '4px'
                        }}
                    >
                        {show3DViewer ? '3D Viewer ON' : '3D Viewer OFF'}
                    </button>
                </div>

                {/* File Info */}
                {selectedFile && (
                    <div style={{ marginBottom: '10px', fontSize: '14px' }}>
                        <strong>📁 Selected:</strong> {selectedFile.name} 
                        <span style={{ color: '#888' }}> ({(selectedFile.size / 1024 / 1024).toFixed(2)} MB)</span>
                    </div>
                )}

                {/* Upload Status */}
                {uploadStatus && (
                    <div style={{ 
                        color: uploadStatus.includes('❌') ? '#ff4444' : '#44ff44',
                        fontWeight: 'bold',
                        fontSize: '14px'
                    }}>
                        {uploadStatus}
                    </div>
                )}
            </div>

            {/* 3D Viewer Area */}
            <div style={{ flex: 1, position: 'relative' }}>
                {show3DViewer ? (
                    <ModelViewer 
                        modelUrl={modelUrl} 
                        showTestCube={showTestCube}
                    />
                ) : (
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        height: '100%',
                        backgroundColor: '#333'
                    }}>
                        <div style={{ textAlign: 'center' }}>
                            <h2 style={{ color: '#00ffff' }}>🎯 3D Model Viewer</h2>
                            <p>Click "3D Viewer ON" to activate the viewer</p>
                            <p>Then upload a 3D model or show test cube</p>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default App;