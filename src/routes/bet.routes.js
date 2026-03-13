import { Router } from 'express';
import { placeBet, getUserBets } from '../controllers/bet.controller.js';
import { authenticate } from '../middleware/auth.middleware.js';

const router = Router();

router.use(authenticate);
router.post('/', placeBet);
router.get('/', getUserBets);

export default router;
