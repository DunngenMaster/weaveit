# Start Electron App on Windows
$env:NODE_ENV = "development"
$env:VITE_DEV_SERVER_URL = "http://127.0.0.1:5174"

# Start Vite dev server and Electron concurrently
npm run dev
