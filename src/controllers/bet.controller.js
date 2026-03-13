import prisma from '../config/prisma.js';
import { z } from 'zod';

const placeBetSchema = z.object({
  stake: z.number().positive().min(1),
  legs: z.array(z.object({
    oddId: z.string(),
  })).min(1),
});

export const placeBet = async (req, res, next) => {
  try {
    const { stake, legs } = placeBetSchema.parse(req.body);
    const userId = req.user.id;

    // Get user balance
    const user = await prisma.user.findUnique({ where: { id: userId }, select: { balance: true } });
    if (user.balance < stake) {
      return res.status(400).json({ error: 'Insufficient balance' });
    }

    // Get odds
    const odds = await prisma.odd.findMany({
      where: { id: { in: legs.map(l => l.oddId) }, isActive: true }
    });
    if (odds.length !== legs.length) {
      return res.status(400).json({ error: 'One or more odds are invalid or unavailable' });
    }

    const totalOdds = odds.reduce((acc, o) => acc * o.value, 1);
    const potential = +(stake * totalOdds).toFixed(2);
    const type = legs.length > 1 ? 'ACCUMULATOR' : 'SINGLE';

    // Create bet + deduct balance in a transaction
    const [bet] = await prisma.$transaction([
      prisma.bet.create({
        data: {
          userId,
          type,
          stake,
          totalOdds: +totalOdds.toFixed(2),
          potential,
          legs: {
            create: odds.map(o => ({ oddId: o.id, oddValue: o.value }))
          }
        },
        include: { legs: true }
      }),
      prisma.user.update({
        where: { id: userId },
        data: { balance: { decrement: stake } }
      }),
      prisma.transaction.create({
        data: { userId, type: 'BET_PLACED', amount: -stake, reference: `Bet placed` }
      })
    ]);

    res.status(201).json({ bet, message: `Bet placed! Potential win: $${potential}` });
  } catch (err) {
    next(err);
  }
};

export const getUserBets = async (req, res, next) => {
  try {
    const { status, page = 1, limit = 10 } = req.query;
    const where = {
      userId: req.user.id,
      ...(status && { status: status.toUpperCase() })
    };

    const [bets, total] = await Promise.all([
      prisma.bet.findMany({
        where,
        include: {
          legs: { include: { odd: { include: { event: { include: { sport: true } } } } } }
        },
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * limit,
        take: Number(limit),
      }),
      prisma.bet.count({ where })
    ]);

    res.json({ bets, total, page: Number(page), pages: Math.ceil(total / limit) });
  } catch (err) {
    next(err);
  }
};
