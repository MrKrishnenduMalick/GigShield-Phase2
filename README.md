# Perfect for Your Worker [ Earn Protector ]

This is an AI-Based Claim Protection System for Delivery Workers. It provides a full-stack platform simulating delivery worker insurance/payout workflows driven by an AI risk detection engine.

## Features

* **Dual-Login System**: Pre-defined users (`raju`, `priya` as Delivery Workers, and `admin` as Platform Manager).
* **Worker Dashboard**: Track protected earnings, coverage, and claim history.
* **AI Fraud Detection**: Simulated check on GPS, weather, and delivery inputs with an animated step-by-step risk calculation logic.
* **Instant Payout Simulation**: Fully animated modal for instantaneous UI feedback upon approved claims.
* **Admin Insights Hub**: Aggregated real-time metrics for Managers showing processed claims and average platform risk. 
* **Real-time Notifications**: Alert system synchronizing user actions to notifications.

## Project Structure

```
project-root/
│── backend/
│   ├── main.py
│   ├── requirements.txt
│── frontend/
│   ├── dashboard.html
│   ├── style.css
│   ├── script.js
│── Dockerfile
│── README.md
```

## Setup Steps

### Local Development

1. **Backend Setup**
   ```bash
   cd backend
   pip install -r requirements.txt
   uvicorn main:app --host 0.0.0.0 --port 10000 --reload
   ```
2. **Frontend Setup**
   Serve the `frontend/` directory using an extension like Live Server in VS Code, or python's `http.server`:
   ```bash
   cd frontend
   python -m http.server 8000
   ```
   *Note: Using a web server avoids CORS issues from using the `file://` protocol.*

## Deployment Guide

### A. Docker / Render Deployment (Backend)
1. Push this codebase to GitHub.
2. Log into Render, create a New Web Service.
3. Connect your GitHub repository.
4. Set Build Command: `pip install -r backend/requirements.txt`
5. Set Start Command: `uvicorn main:app --host 0.0.0.0 --port 10000`

### B. Railway Deployment (Backend)
1. Push codebase to GitHub and connect to Railway.
2. Railway will auto-detect the Python codebase.
3. Override the Start command (if needed) to: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`

### C. Vercel Deployment (Frontend)
1. Deploy the `frontend/` folder directly to Vercel via GitHub or Vercel CLI.
2. Remember to modify `script.js` line 1:
   `const API_BASE_URL = 'http://localhost:10000';`
   Change `localhost:10000` to the deployed Render/Railway backend URL.

## API Endpoints

* `POST /simulate_claim_checks`
  Calculates a dummy risk score given GPS, Weather, and Delivery booleans. Returns a decision.
* `GET /notifications/{user}`
  Retrieves specific state notifications for a user or admin.
* `GET /admin/insights`
  Retrieves global platform statistics.

## GitHub Upload Steps

```bash
git init
git add .
git commit -m "Initial commit - Perfect for Your Worker"
git branch -M main
git remote add origin <your-repo-link>
git push -u origin main
```
