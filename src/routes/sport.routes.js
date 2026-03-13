import { Router } from 'express';
import prisma from '../config/prisma.js';

const router = Router();

router.get('/', async (req, res, next) => {
  try {
    const sports = await prisma.sport.findMany({
      where: { isActive: true },
      include: { _count: { select: { events: true } } }
    });
    res.json({ sports });
  } catch (err) { next(err); }
});

export default router;
