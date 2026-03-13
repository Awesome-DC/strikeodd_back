import { Router } from 'express';
import { getEvents, getEventById, getLiveEvents } from '../controllers/event.controller.js';

const router = Router();

router.get('/', getEvents);
router.get('/live', getLiveEvents);
router.get('/:id', getEventById);

export default router;
