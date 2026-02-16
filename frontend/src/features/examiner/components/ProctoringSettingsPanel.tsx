import React, { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import {
  Camera,
  Mic,
  Eye,
  Users,
  Monitor,
  Activity,
  Settings,
  Save,
  Info,
  Shield,
  AlertCircle
} from 'lucide-react';
import api from '@/lib/api';

interface ProctoringSettings {
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

interface ProctoringSettingsProps {
  examId: string;
  onSave?: (settings: ProctoringSettings) => void;
}

const defaultSettings: ProctoringSettings = {
  camera_enabled: true,
  microphone_enabled: false,
  face_detection_enabled: true,
  multiple_face_detection: true,
  head_pose_detection: true,
  tab_switch_detection: true,
  min_face_confidence: 0.6,
  max_head_rotation: 30.0,
  detection_interval: 2,
  initial_health: 100,
  auto_submit_on_zero_health: true,
  health_warning_threshold: 40
};

const ProctoringSettingsPanel: React.FC<ProctoringSettingsProps> = ({ 
  examId, 
  onSave 
}) => {
  const [settings, setSettings] = useState<ProctoringSettings>(defaultSettings);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadSettings();
  }, [examId]);

  const loadSettings = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/monitor/exam/${examId}/proctoring-settings`);
      setSettings(response.data);
    } catch (err: any) {
      console.error('Failed to load proctoring settings:', err);
      // Use default settings if loading fails
      setSettings(defaultSettings);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      
      await api.post(`/monitor/exam/${examId}/proctoring-settings`, settings);
      
      setSuccessMessage('Proctoring settings saved successfully!');
      setTimeout(() => setSuccessMessage(null), 3000);
      
      if (onSave) {
        onSave(settings);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const ToggleSwitch: React.FC<{
    enabled: boolean;
    onChange: (value: boolean) => void;
    label: string;
    description?: string;
    icon: React.ReactNode;
    disabled?: boolean;
  }> = ({ enabled, onChange, label, description, icon, disabled }) => (
    <div className={`p-4 rounded-lg border transition-all ${
      enabled && !disabled
        ? 'bg-indigo-50 border-indigo-200' 
        : 'bg-slate-50 border-slate-200'
    } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}>
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3 flex-1">
          <div className={`mt-1 ${enabled && !disabled ? 'text-indigo-600' : 'text-slate-400'}`}>
            {icon}
          </div>
          <div className="flex-1">
            <label className="font-semibold text-slate-900 cursor-pointer">
              {label}
            </label>
            {description && (
              <p className="text-sm text-slate-600 mt-1">{description}</p>
            )}
          </div>
        </div>
        
        <button
          onClick={() => !disabled && onChange(!enabled)}
          disabled={disabled}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
            enabled && !disabled ? 'bg-indigo-600' : 'bg-slate-300'
          } ${disabled ? 'cursor-not-allowed' : 'cursor-pointer'}`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
              enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>
    </div>
  );

  const SliderInput: React.FC<{
    value: number;
    onChange: (value: number) => void;
    label: string;
    min: number;
    max: number;
    step: number;
    unit?: string;
    description?: string;
  }> = ({ value, onChange, label, min, max, step, unit, description }) => (
    <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
      <div className="flex items-center justify-between mb-2">
        <label className="font-semibold text-slate-900">{label}</label>
        <span className="text-lg font-bold text-indigo-600">
          {value}{unit}
        </span>
      </div>
      {description && (
        <p className="text-sm text-slate-600 mb-3">{description}</p>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-indigo-600"
      />
      <div className="flex justify-between text-xs text-slate-500 mt-1">
        <span>{min}{unit}</span>
        <span>{max}{unit}</span>
      </div>
    </div>
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center p-12">
        <div className="w-12 h-12 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <Shield className="w-6 h-6 text-indigo-600" />
          <h2 className="text-2xl font-bold text-slate-900">Proctoring Settings</h2>
        </div>
        <p className="text-slate-600">
          Configure AI-powered proctoring features and health monitoring for this exam
        </p>
      </div>

      {/* Error Message */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="mb-6 p-4 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-3"
        >
          <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-rose-900">Error</p>
            <p className="text-sm text-rose-700">{error}</p>
          </div>
        </motion.div>
      )}

      {/* Success Message */}
      {successMessage && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          className="mb-6 p-4 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start gap-3"
        >
          <Settings className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
          <div>
            <p className="font-semibold text-emerald-900">Success</p>
            <p className="text-sm text-emerald-700">{successMessage}</p>
          </div>
        </motion.div>
      )}

      <div className="space-y-6">
        {/* Primary Features */}
        <section>
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Activity className="w-5 h-5 text-indigo-600" />
            Primary Monitoring Features
          </h3>
          
          <div className="space-y-3">
            <ToggleSwitch
              enabled={settings.camera_enabled}
              onChange={(value) => setSettings({ ...settings, camera_enabled: value })}
              label="Camera Monitoring"
              description="Enable webcam access for visual proctoring"
              icon={<Camera className="w-5 h-5" />}
            />

            <ToggleSwitch
              enabled={settings.microphone_enabled}
              onChange={(value) => setSettings({ ...settings, microphone_enabled: value })}
              label="Microphone Monitoring"
              description="Enable audio monitoring to detect conversations and suspicious sounds"
              icon={<Mic className="w-5 h-5" />}
            />

            <ToggleSwitch
              enabled={settings.tab_switch_detection}
              onChange={(value) => setSettings({ ...settings, tab_switch_detection: value })}
              label="Tab Switch Detection"
              description="Flag when student switches browser tabs or windows"
              icon={<Monitor className="w-5 h-5" />}
            />
          </div>
        </section>

        {/* Face Detection Features */}
        <section>
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Eye className="w-5 h-5 text-indigo-600" />
            Face Detection Features
          </h3>
          
          <div className="space-y-3">
            <ToggleSwitch
              enabled={settings.face_detection_enabled}
              onChange={(value) => setSettings({ ...settings, face_detection_enabled: value })}
              label="Face Detection"
              description="Verify that a face is visible in the camera frame"
              icon={<Eye className="w-5 h-5" />}
              disabled={!settings.camera_enabled}
            />

            <ToggleSwitch
              enabled={settings.multiple_face_detection}
              onChange={(value) => setSettings({ ...settings, multiple_face_detection: value })}
              label="Multiple Face Detection"
              description="Alert when more than one face is detected (indicates possible help)"
              icon={<Users className="w-5 h-5" />}
              disabled={!settings.camera_enabled || !settings.face_detection_enabled}
            />

            <ToggleSwitch
              enabled={settings.head_pose_detection}
              onChange={(value) => setSettings({ ...settings, head_pose_detection: value })}
              label="Head Pose Detection"
              description="Monitor if student is looking away from the screen"
              icon={<Activity className="w-5 h-5" />}
              disabled={!settings.camera_enabled || !settings.face_detection_enabled}
            />
          </div>
        </section>

        {/* Detection Parameters */}
        <section>
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Settings className="w-5 h-5 text-indigo-600" />
            Detection Parameters
          </h3>
          
          <div className="space-y-3">
            <SliderInput
              value={settings.min_face_confidence}
              onChange={(value) => setSettings({ ...settings, min_face_confidence: value })}
              label="Minimum Face Confidence"
              description="Lower values = more lenient detection (may flag poor lighting)"
              min={0.3}
              max={0.9}
              step={0.05}
            />

            <SliderInput
              value={settings.max_head_rotation}
              onChange={(value) => setSettings({ ...settings, max_head_rotation: value })}
              label="Maximum Head Rotation"
              description="Maximum allowed head rotation before flagging (in degrees)"
              min={15}
              max={60}
              step={5}
              unit="°"
            />

            <SliderInput
              value={settings.detection_interval}
              onChange={(value) => setSettings({ ...settings, detection_interval: value })}
              label="Detection Interval"
              description="How often to analyze frames (lower = more frequent checks)"
              min={1}
              max={10}
              step={1}
              unit="s"
            />
          </div>
        </section>

        {/* Health System */}
        <section>
          <h3 className="text-lg font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <Shield className="w-5 h-5 text-indigo-600" />
            Health System Configuration
          </h3>
          
          <div className="space-y-3">
            <SliderInput
              value={settings.initial_health}
              onChange={(value) => setSettings({ ...settings, initial_health: value })}
              label="Initial Health"
              description="Starting health points for each student"
              min={50}
              max={200}
              step={10}
            />

            <SliderInput
              value={settings.health_warning_threshold}
              onChange={(value) => setSettings({ ...settings, health_warning_threshold: value })}
              label="Health Warning Threshold"
              description="Show warning when health drops below this percentage"
              min={20}
              max={60}
              step={5}
              unit="%"
            />

            <ToggleSwitch
              enabled={settings.auto_submit_on_zero_health}
              onChange={(value) => setSettings({ ...settings, auto_submit_on_zero_health: value })}
              label="Auto-Submit on Zero Health"
              description="Automatically submit exam when student's health reaches zero"
              icon={<AlertCircle className="w-5 h-5" />}
            />
          </div>
        </section>

        {/* Health Penalties Info */}
        <section className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-start gap-3">
            <Info className="w-5 h-5 text-blue-600 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-semibold text-blue-900 mb-2">Health Penalty System</h4>
              <div className="text-sm text-blue-800 space-y-1">
                <p>• <strong>No Face Detected:</strong> -10 health (High severity: -15)</p>
                <p>• <strong>Multiple Faces:</strong> -15 health (High severity: -23)</p>
                <p>• <strong>Looking Away:</strong> -5 health (High severity: -8)</p>
                <p>• <strong>Tab Switch:</strong> -8 health (High severity: -12)</p>
                <p>• <strong>Suspicious Audio:</strong> -3 health (Low severity)</p>
              </div>
            </div>
          </div>
        </section>

        {/* Save Button */}
        <div className="flex items-center justify-end gap-4 pt-6 border-t border-slate-200">
          <button
            onClick={loadSettings}
            className="btn-secondary"
            disabled={saving}
          >
            Reset to Saved
          </button>
          
          <button
            onClick={handleSave}
            disabled={saving}
            className="btn-primary flex items-center gap-2"
          >
            {saving ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                <span>Saving...</span>
              </>
            ) : (
              <>
                <Save className="w-4 h-4" />
                <span>Save Settings</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProctoringSettingsPanel;