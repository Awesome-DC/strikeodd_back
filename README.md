# ⚡ StrikeOdds — Full Stack Betting Platform

A multi-sport betting site built with React + Node.js + PostgreSQL.

## Tech Stack

| Layer | Tech |
|-------|------|
| Frontend | React 18, Vite, React Router, Zustand |
| Backend | Node.js, Express, Prisma ORM |
| Database | PostgreSQL |
| Auth | JWT + bcryptjs |
| Deploy | Vercel (frontend) + Railway (backend + DB) |

---

## 🚀 Local Setup

### Prerequisites
- Node.js 18+
- PostgreSQL running locally

### 1. Clone & Install

```bash
git clone <your-repo>
cd strikeodds
npm run install:all
```

### 2. Setup Environment

```bash
cd server
cp .env.example .env
# Edit .env with your PostgreSQL connection string
```

### 3. Setup Database

```bash
cd server
npm run db:generate    # Generate Prisma client
npm run db:migrate     # Run migrations
npm run db:seed        # Seed with sample data
```

### 4. Run Development

```bash
# From root directory - starts both frontend and backend
npm run dev
```

### 5. Demo Login
```
Email: demo@strikeodds.com
Password: password123
```

---


## 🚢 Deployment

### Frontend → Vercel
```bash
cd client && npm run build
# Deploy /dist to Vercel
# Set VITE_API_URL env variable
```

### Backend → Railway
```
1. Connect GitHub repo on Railway
2. Set root directory to /server
3. Add PostgreSQL service
4. Set DATABASE_URL, JWT_SECRET env vars
```
