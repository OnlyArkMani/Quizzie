/* ================================
   Proctoring & Monitoring Types
================================ */

export interface ProctoringSettings {
  camera_enabled: boolean;
  microphone_enabled: boolean;
  face_detection_enabled: boolean;
  multiple_face_detection: boolean;
  head_pose_detection: boolean;
  tab_switch_detection: boolean;
  min_face_confidence: number;
  max_head_rotation: number;
  detection_interval: number;
  initial_health: number;
  auto_submit_on_zero_health: boolean;
  health_warning_threshold: number;
}

export interface HealthStatus {
  current: number;
  max: number;
  percentage: number;
  status: 'good' | 'warning' | 'critical' | 'failed';
  violations_count: number;
}

export interface ViolationFlag {
  type: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

/* ================================
   Core Domain Types
================================ */

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'student' | 'examiner' | 'admin';
  created_at: string;
}

export interface Exam {
  id: string;
  title: string;
  description: string;
  duration_minutes: number;
  total_marks: number;
  pass_percentage: number;
  status: 'draft' | 'live' | 'ended';
  start_time?: string;
  end_time?: string;
  created_by: string;
  created_at: string;
  question_count?: number;
}

export interface Question {
  id: string;
  exam_id: string;
  question_text: string;
  question_type: 'single' | 'multiple';
  marks: number;
  topic?: string;
  display_order: number;
  options: Option[];
}

export interface Option {
  id: string;
  question_id: string;
  option_text: string;
  is_correct: boolean;
  display_order: number;
}

export interface Answer {
  questionId: string;
  selectedOptions: number[];
  markedForReview: boolean;
  visited: boolean;
}

export interface ExamAttempt {
  id: string;
  exam_id: string;
  student_id: string;
  started_at: string;
  submitted_at?: string;
  time_taken_seconds?: number;
  score?: number;
  status: 'in_progress' | 'submitted' | 'evaluated';
  cheating_flags: number;
}

export interface Response {
  id: string;
  attempt_id: string;
  question_id: string;
  selected_option_ids: string[];
  is_correct?: boolean;
  marks_awarded?: number;
  marked_for_review: boolean;
}

export interface CheatLog {
  id: string;
  attempt_id: string;
  flag_type: string;
  severity: 'low' | 'medium' | 'high';
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface AnalyticsSummary {
  total_attempts: number;
  average_score: number;
  highest_score: number;
  lowest_score: number;
  pass_percentage: number;
  topic_wise_stats: Record<
    string,
    {
      correct: number;
      total: number;
      percentage: number;
    }
  >;
}

export interface LeaderboardEntry {
  student_name: string;
  score: number;
  time_taken_seconds: number;
  rank: number;
}
