# Deploy to Render (Free Forever)

## Step 1: Push to GitHub
```bash
cd d:\DEPLOY-X
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin YOUR_GITHUB_REPO_URL
git push -u origin main
```

## Step 2: Deploy on Render
1. Go to: https://render.com
2. Sign up with GitHub
3. Click "New +" → "Web Service"
4. Connect your GitHub repo
5. Settings:
   - **Name**: `ece-attendance`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python app.py`
   - **Plan**: `Free`

## Step 3: Add Environment Variables
In Render dashboard, go to "Environment" and add:
- `MONGO_URI` = (your MongoDB connection string)
- `SECRET_KEY` = (your secret key from .env)
- `ADMIN_USERNAME` = ECEADMIN
- `ADMIN_PASSWORD` = DEPLOYX@2025

## Step 4: Deploy
Click "Create Web Service" and wait 2-3 minutes.

Your site will be live at: `https://ece-attendance.onrender.com`

## Mobile Access:
✅ HTTPS works automatically
✅ Camera/QR scanner will work
✅ Real-time updates work perfectly

## Important Notes:
- Free tier sleeps after 15min inactivity
- First load after sleep: ~50 seconds
- During your event (active use): stays awake, instant
- Forever free, no credit limits
