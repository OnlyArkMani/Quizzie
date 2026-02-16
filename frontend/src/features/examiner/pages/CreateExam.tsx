import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import { Check } from 'lucide-react';

import { useExaminerStore } from '../store/examinerStore';
import Step1Details from '../components/ExamWizard/Step1Details';
import Step2Questions from '../components/ExamWizard/Step2Questions';
import Step3Settings from '../components/ExamWizard/Step3Settings';
import ProctoringSettingsPanel from '../components/ProctoringSettingsPanel';

const CreateExam = () => {
  const navigate = useNavigate();

  const {
    currentStep,
    examId, // must be set after Step 1
  } = useExaminerStore();

  useEffect(() => {
    // Intentionally left empty
    // Draft persistence can be added later
  }, []);

  const steps = [
    { number: 1, title: 'Exam Details', component: Step1Details },
    { number: 2, title: 'Add Questions', component: Step2Questions },
    { number: 3, title: 'Settings & Publish', component: Step3Settings },
  ];

  const CurrentStepComponent = steps[currentStep - 1].component;

  return (
    <div className="min-h-screen bg-slate-50 py-8 px-4">
      <div className="max-w-5xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <button
            onClick={() => navigate('/examiner')}
            className="text-sm text-slate-600 hover:text-slate-900 mb-4"
          >
            ← Back to Dashboard
          </button>
          <h1 className="text-3xl font-bold text-slate-900">
            Create New Exam
          </h1>
          <p className="text-slate-600 mt-2">
            Follow the steps to create your exam
          </p>
        </div>

        {/* Progress Steps */}
        <div className="card p-6 mb-8">
          <div className="flex items-center justify-between">
            {steps.map((step, index) => (
              <div key={step.number} className="flex items-center flex-1">
                <div className="flex items-center">
                  {/* Step Circle */}
                  <motion.div
                    initial={false}
                    animate={{
                      backgroundColor:
                        currentStep > step.number
                          ? '#10b981'
                          : currentStep === step.number
                          ? '#4f46e5'
                          : '#e2e8f0',
                    }}
                    className="w-10 h-10 rounded-full flex items-center justify-center"
                  >
                    {currentStep > step.number ? (
                      <Check className="w-5 h-5 text-white" />
                    ) : (
                      <span
                        className={`font-semibold ${
                          currentStep === step.number
                            ? 'text-white'
                            : 'text-slate-600'
                        }`}
                      >
                        {step.number}
                      </span>
                    )}
                  </motion.div>

                  {/* Step Title */}
                  <div className="ml-3">
                    <p
                      className={`text-sm font-medium ${
                        currentStep >= step.number
                          ? 'text-slate-900'
                          : 'text-slate-500'
                      }`}
                    >
                      {step.title}
                    </p>
                  </div>
                </div>

                {/* Connector Line */}
                {index < steps.length - 1 && (
                  <div className="flex-1 mx-4">
                    <motion.div
                      initial={false}
                      animate={{
                        backgroundColor:
                          currentStep > step.number
                            ? '#10b981'
                            : '#e2e8f0',
                      }}
                      className="h-1 rounded-full"
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Step Content */}
        <motion.div
          key={currentStep}
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -20 }}
          transition={{ duration: 0.3 }}
        >
          <CurrentStepComponent />

          {/* Step 3: Proctoring Settings */}
          {currentStep === 3 && examId && (
            <div className="mt-8">
              <ProctoringSettingsPanel
                examId={examId}
                onSave={(settings) => {
                  console.log(
                    'Proctoring settings saved:',
                    settings
                  );
                  // Optional:
                  // - show success toast
                  // - enable Publish button
                }}
              />
            </div>
          )}
        </motion.div>
      </div>
    </div>
  );
};

export default CreateExam;
