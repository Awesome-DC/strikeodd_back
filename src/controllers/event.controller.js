import prisma from '../config/prisma.js';

export const getEvents = async (req, res, next) => {
  try {
    const { sport, status = 'UPCOMING', page = 1, limit = 20 } = req.query;

    const where = {
      status: status.toUpperCase(),
      ...(sport && { sport: { slug: sport } })
    };

    const [events, total] = await Promise.all([
      prisma.event.findMany({
        where,
        include: {
          sport: { select: { name: true, slug: true, icon: true } },
          odds: { where: { isActive: true } },
        },
        orderBy: { startTime: 'asc' },
        skip: (page - 1) * limit,
        take: Number(limit),
      }),
      prisma.event.count({ where })
    ]);

    res.json({ events, total, page: Number(page), pages: Math.ceil(total / limit) });
  } catch (err) {
    next(err);
  }
};

export const getEventById = async (req, res, next) => {
  try {
    const event = await prisma.event.findUnique({
      where: { id: req.params.id },
      include: {
        sport: true,
        odds: { where: { isActive: true } },
      }
    });
    if (!event) return res.status(404).json({ error: 'Event not found' });
    res.json({ event });
  } catch (err) {
    next(err);
  }
};

export const getLiveEvents = async (req, res, next) => {
  try {
    const events = await prisma.event.findMany({
      where: { status: 'LIVE' },
      include: {
        sport: { select: { name: true, slug: true, icon: true } },
        odds: { where: { isActive: true } },
      },
      orderBy: { startTime: 'asc' },
    });
    res.json({ events });
  } catch (err) {
    next(err);
  }
};
