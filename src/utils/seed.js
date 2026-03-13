import { PrismaClient } from '@prisma/client';
import bcrypt from 'bcryptjs';

const prisma = new PrismaClient();

async function main() {
  console.log('🌱 Seeding database...');

  // Sports
  const sports = await Promise.all([
    prisma.sport.upsert({ where: { slug: 'football' }, update: {}, create: { name: 'Football', slug: 'football', icon: '⚽' } }),
    prisma.sport.upsert({ where: { slug: 'basketball' }, update: {}, create: { name: 'Basketball', slug: 'basketball', icon: '🏀' } }),
    prisma.sport.upsert({ where: { slug: 'tennis' }, update: {}, create: { name: 'Tennis', slug: 'tennis', icon: '🎾' } }),
    prisma.sport.upsert({ where: { slug: 'cricket' }, update: {}, create: { name: 'Cricket', slug: 'cricket', icon: '🏏' } }),
    prisma.sport.upsert({ where: { slug: 'boxing' }, update: {}, create: { name: 'Boxing', slug: 'boxing', icon: '🥊' } }),
  ]);

  const football = sports[0];
  const basketball = sports[1];

  // Events
  const now = new Date();
  const events = [
    {
      sportId: football.id, homeTeam: 'Manchester City', awayTeam: 'Arsenal',
      startTime: new Date(now.getTime() + 2 * 60 * 60 * 1000),
      status: 'UPCOMING', league: 'Premier League', country: 'England',
    },
    {
      sportId: football.id, homeTeam: 'Real Madrid', awayTeam: 'Barcelona',
      startTime: new Date(now.getTime() + 4 * 60 * 60 * 1000),
      status: 'UPCOMING', league: 'La Liga', country: 'Spain',
    },
    {
      sportId: football.id, homeTeam: 'PSG', awayTeam: 'Bayern Munich',
      startTime: new Date(now.getTime() - 30 * 60 * 1000),
      status: 'LIVE', league: 'Champions League', homeScore: 1, awayScore: 0,
    },
    {
      sportId: basketball.id, homeTeam: 'LA Lakers', awayTeam: 'Golden State Warriors',
      startTime: new Date(now.getTime() + 6 * 60 * 60 * 1000),
      status: 'UPCOMING', league: 'NBA', country: 'USA',
    },
    {
      sportId: basketball.id, homeTeam: 'Boston Celtics', awayTeam: 'Miami Heat',
      startTime: new Date(now.getTime() - 45 * 60 * 1000),
      status: 'LIVE', league: 'NBA', homeScore: 67, awayScore: 54,
    },
  ];

  for (const eventData of events) {
    const event = await prisma.event.create({ data: eventData });

    // Create odds for each event
    if (event.sportId === football.id) {
      await prisma.odd.createMany({
        data: [
          { eventId: event.id, market: '1X2', selection: 'Home', value: +(1.5 + Math.random()).toFixed(2) },
          { eventId: event.id, market: '1X2', selection: 'Draw', value: +(2.8 + Math.random() * 0.5).toFixed(2) },
          { eventId: event.id, market: '1X2', selection: 'Away', value: +(2.5 + Math.random() * 1.5).toFixed(2) },
          { eventId: event.id, market: 'BTTS', selection: 'Yes', value: +(1.6 + Math.random() * 0.4).toFixed(2) },
          { eventId: event.id, market: 'BTTS', selection: 'No', value: +(2.0 + Math.random() * 0.5).toFixed(2) },
          { eventId: event.id, market: 'Over/Under', selection: 'Over 2.5', value: +(1.8 + Math.random() * 0.4).toFixed(2) },
          { eventId: event.id, market: 'Over/Under', selection: 'Under 2.5', value: +(1.9 + Math.random() * 0.4).toFixed(2) },
        ]
      });
    } else {
      await prisma.odd.createMany({
        data: [
          { eventId: event.id, market: 'Moneyline', selection: 'Home', value: +(1.5 + Math.random()).toFixed(2) },
          { eventId: event.id, market: 'Moneyline', selection: 'Away', value: +(2.0 + Math.random()).toFixed(2) },
          { eventId: event.id, market: 'Over/Under', selection: 'Over 210.5', value: +(1.85 + Math.random() * 0.2).toFixed(2) },
          { eventId: event.id, market: 'Over/Under', selection: 'Under 210.5', value: +(1.85 + Math.random() * 0.2).toFixed(2) },
        ]
      });
    }
  }

  // Demo user
  const password = await bcrypt.hash('password123', 12);
  await prisma.user.upsert({
    where: { email: 'demo@strikeodds.com' },
    update: {},
    create: {
      email: 'demo@strikeodds.com',
      username: 'demo_user',
      password,
      firstName: 'Demo',
      lastName: 'User',
      balance: 1000,
      transactions: { create: { type: 'DEPOSIT', amount: 1000, reference: 'Welcome bonus' } }
    }
  });

  console.log('✅ Seed complete!');
  console.log('📧 Demo login: demo@strikeodds.com / password123');
}

main().catch(console.error).finally(() => prisma.$disconnect());
