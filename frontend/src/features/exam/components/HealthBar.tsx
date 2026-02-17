import React, { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Heart,
  AlertTriangle,
  Eye,
  Users,
  Activity,
  ShieldAlert,
  CheckCircle,
  XCircle
} from 'lucide-react';

interface HealthStatus {
  current: number;
  max: number;
  percentage: number;
  status: 'good' | 'warning' | 'critical' | 'failed';
  violations_count: number;
}

interface Violation {
  type: string;
  severity: 'low' | 'medium' | 'high';
  message: string;
  timestamp: string;
}

interface HealthBarProps {
  attemptId: string;
  onHealthZero?: () => void;
  showViolations?: boolean;
}

const HealthBar: React.FC<HealthBarProps> = ({
  attemptId,
  onHealthZero,
  showViolations = true
}) => {
  const [health, setHealth] = useState<HealthStatus>({
    current: 100,
    max: 100,
    percentage: 100,
    status: 'good',
    violations_count: 0
  });

  const [recentViolations, setRecentViolations] = useState<Violation[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const [showAlert, setShowAlert] = useState(false);

  // WebSocket connection for real-time updates
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname;

    // FIX Bug 7: Correct WS path — backend mounts enhanced_monitoring at
    // /api/v1/monitor/enhanced, so the WS endpoint is:
    // /api/v1/monitor/enhanced/ws/proctoring/{attempt_id}
    const wsUrl = `${protocol}//${host}:8000/api/v1/monitor/enhanced/ws/proctoring/${attemptId}`;

    let websocket: WebSocket;
    let reconnectTimeout: NodeJS.Timeout;

    const connect = () => {
      websocket = new WebSocket(wsUrl);

      websocket.onopen = () => {
        console.log('✅ Proctoring WebSocket connected');
        setIsConnected(true);
      };

      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === 'health_update') {
            const newHealth = data.data as HealthStatus;
            setHealth(newHealth);

            if (newHealth.percentage <= 40 && newHealth.percentage > 0) {
              setShowAlert(true);
              setTimeout(() => setShowAlert(false), 3000);
            }

            if (newHealth.percentage <= 0 && onHealthZero) {
              onHealthZero();
            }
          }

          if (data.type === 'violation_alert') {
            const violation = data.data as Violation;
            setRecentViolations(prev => [violation, ...prev].slice(0, 5));
          }
        } catch (e) {
          console.error('WS message parse error:', e);
        }
      };

      websocket.onerror = () => {
        setIsConnected(false);
      };

      websocket.onclose = () => {
        setIsConnected(false);
        // Auto-reconnect after 5 seconds
        reconnectTimeout = setTimeout(connect, 5000);
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimeout);
      websocket?.close();
    };
  }, [attemptId, onHealthZero]);

  const getHealthColor = useCallback(() => {
    if (health.percentage > 70) return 'bg-emerald-500';
    if (health.percentage > 40) return 'bg-amber-500';
    if (health.percentage > 0) return 'bg-rose-500';
    return 'bg-gray-500';
  }, [health.percentage]);

  const getHealthTextColor = useCallback(() => {
    if (health.percentage > 70) return 'text-emerald-600';
    if (health.percentage > 40) return 'text-amber-600';
    if (health.percentage > 0) return 'text-rose-600';
    return 'text-gray-600';
  }, [health.percentage]);

  const getStatusIcon = useCallback(() => {
    switch (health.status) {
      case 'good': return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case 'warning': return <AlertTriangle className="w-5 h-5 text-amber-500" />;
      case 'critical': return <ShieldAlert className="w-5 h-5 text-rose-500" />;
      case 'failed': return <XCircle className="w-5 h-5 text-gray-500" />;
      default: return <Activity className="w-5 h-5" />;
    }
  }, [health.status]);

  const getViolationIcon = (type: string) => {
    switch (type) {
      case 'no_face':
      case 'looking_away': return <Eye className="w-4 h-4" />;
      case 'multiple_faces': return <Users className="w-4 h-4" />;
      case 'tab_switch': return <Activity className="w-4 h-4" />;
      default: return <AlertTriangle className="w-4 h-4" />;
    }
  };

  return (
    <div className="fixed top-4 right-4 z-50 w-80">
      {/* Connection Status */}
      <div className="mb-2 flex items-center justify-end gap-2 text-xs">
        <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500' : 'bg-rose-500'} animate-pulse`} />
        <span className="text-slate-400">
          {isConnected ? 'Monitoring Active' : 'Reconnecting...'}
        </span>
      </div>

      {/* Health Bar Card */}
      <motion.div
        initial={{ opacity: 0, y: -20 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-white rounded-xl shadow-lg border border-slate-200 p-4"
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Heart className={`w-5 h-5 ${getHealthTextColor()}`} />
            <span className="font-semibold text-slate-900">Exam Health</span>
          </div>
          {getStatusIcon()}
        </div>

        <div className="relative">
          <div className="w-full h-8 bg-slate-100 rounded-full overflow-hidden">
            <motion.div
              className={`h-full ${getHealthColor()} flex items-center justify-end pr-3`}
              initial={{ width: '100%' }}
              animate={{ width: `${Math.max(health.percentage, 0)}%` }}
              transition={{ duration: 0.5, ease: 'easeOut' }}
            >
              <span className="text-xs font-bold text-white drop-shadow">
                {health.current}/{health.max}
              </span>
            </motion.div>
          </div>

          <div className="flex items-center justify-between mt-2">
            <span className={`text-2xl font-bold ${getHealthTextColor()}`}>
              {health.percentage.toFixed(0)}%
            </span>
            <span className="text-xs text-slate-500 uppercase font-semibold">
              {health.status}
            </span>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-slate-100">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-600">Total Violations</span>
            <span className={`font-semibold ${health.violations_count > 10 ? 'text-rose-600' : 'text-slate-900'}`}>
              {health.violations_count}
            </span>
          </div>
        </div>

        <div className="mt-3 pt-3 border-t border-slate-100 space-y-1 text-xs">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-emerald-500 rounded" />
            <span className="text-slate-600">Good (70%+)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-amber-500 rounded" />
            <span className="text-slate-600">Warning (40–70%)</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 bg-rose-500 rounded" />
            <span className="text-slate-600">Critical (&lt;40%)</span>
          </div>
        </div>
      </motion.div>

      {/* Recent Violations */}
      {showViolations && recentViolations.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mt-3 bg-white rounded-xl shadow-lg border border-slate-200 p-3"
        >
          <h3 className="text-sm font-semibold text-slate-900 mb-2">Recent Flags</h3>
          <div className="space-y-2">
            <AnimatePresence>
              {recentViolations.slice(0, 3).map((violation, index) => (
                <motion.div
                  key={`${violation.type}-${violation.timestamp}-${index}`}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 10 }}
                  className={`flex items-start gap-2 p-2 rounded-lg text-xs ${
                    violation.severity === 'high' ? 'bg-rose-50 border border-rose-200' :
                    violation.severity === 'medium' ? 'bg-amber-50 border border-amber-200' :
                    'bg-blue-50 border border-blue-200'
                  }`}
                >
                  <div className={`mt-0.5 ${
                    violation.severity === 'high' ? 'text-rose-600' :
                    violation.severity === 'medium' ? 'text-amber-600' :
                    'text-blue-600'
                  }`}>
                    {getViolationIcon(violation.type)}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-slate-900">{violation.message}</p>
                    <p className="text-slate-500 text-xs mt-0.5">
                      {new Date(violation.timestamp).toLocaleTimeString()}
                    </p>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        </motion.div>
      )}

      {/* Critical Health Alert */}
      <AnimatePresence>
        {showAlert && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            className="mt-3 bg-gradient-to-r from-rose-500 to-orange-500 text-white rounded-xl shadow-lg p-4"
          >
            <div className="flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 animate-pulse" />
              <div>
                <p className="font-bold">Health Warning!</p>
                <p className="text-sm opacity-90">Your exam health is low. Please maintain focus.</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Zero Health */}
      <AnimatePresence>
        {health.percentage <= 0 && (
          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="mt-3 bg-gray-900 text-white rounded-xl shadow-lg p-4"
          >
            <div className="flex items-center gap-3">
              <XCircle className="w-6 h-6" />
              <div>
                <p className="font-bold">Exam Health Depleted</p>
                <p className="text-sm opacity-90">Your exam will be auto-submitted.</p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default HealthBar;