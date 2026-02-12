export const APP_NAME = 'Quizzie';
export const APP_DESCRIPTION = 'Smart Online Examination Platform';

export const ROUTES = {
  HOME: '/',
  LOGIN: '/login',
  REGISTER: '/register',
  
  // Student
  STUDENT_DASHBOARD: '/student',
  EXAM_LOBBY: '/student/exam/:examId/lobby',
  TAKE_EXAM: '/student/exam/:examId/take',
  EXAM_RESULTS: '/student/exam/:examId/results',
  
  // Examiner
  EXAMINER_DASHBOARD: '/examiner',
  CREATE_EXAM: '/examiner/exam/create',
  MANAGE_EXAMS: '/examiner/exams',
  EXAM_ANALYTICS: '/examiner/exam/:examId/analytics',
  
  // Misc
  UNAUTHORIZED: '/unauthorized',
  NOT_FOUND: '*',
};

export const EXAM_STATUS = {
  DRAFT: 'draft',
  LIVE: 'live',
  ENDED: 'ended',
} as const;

export const QUESTION_TYPES = {
  SINGLE: 'single',
  MULTIPLE: 'multiple',
} as const;

export const USER_ROLES = {
  STUDENT: 'student',
  EXAMINER: 'examiner',
  ADMIN: 'admin',
} as const;

export const CHEAT_FLAGS = {
  NO_FACE: 'no_face_detected',
  MULTIPLE_FACES: 'multiple_faces_detected',
  LOOKING_AWAY: 'looking_away',
  TAB_SWITCH: 'tab_switch',
  LOUD_NOISE: 'loud_noise_detected',
  MULTIPLE_VOICES: 'multiple_voices_detected',
} as const;

export const STORAGE_KEYS = {
  AUTH_TOKEN: 'auth-storage',
} as const;