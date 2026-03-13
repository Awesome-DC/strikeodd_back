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

- Frontend: http://localhost:5173
- Backend API: http://localhost:5000/api

### 5. Demo Login
```
Email: demo@strikeodds.com
Password: password123
```

---

## 📁 Project Structure

```
strikeodds/
├── client/                  # React frontend
│   └── src/
│       ├── pages/           # Route pages
│       ├── components/      # UI components
│       │   ├── ui/          # Base components
│       │   ├── layout/      # Layout (Navbar, Sidebar)
│       │   └── betting/     # Betslip, OddsCard
│       ├── context/         # Auth + Betslip state
│       ├── services/        # API calls (axios)
│       └── hooks/           # Custom hooks
│
└── server/                  # Express backend
    ├── prisma/
    │   └── schema.prisma    # Database schema
    └── src/
        ├── controllers/     # Business logic
        ├── routes/          # API routes
        ├── middleware/      # Auth, error handling
        └── utils/           # Seed, helpers
```

---

## 🌐 API Endpoints

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/auth/register | Create account |
| POST | /api/auth/login | Login |
| GET | /api/auth/me | Get current user |

### Events
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/events | Get all events |
| GET | /api/events/live | Get live events |
| GET | /api/events/:id | Get single event |

### Bets
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/bets | Place a bet |
| GET | /api/bets | Get my bets |

### User
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /api/users/profile | Get profile |
| GET | /api/users/transactions | Transaction history |

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
