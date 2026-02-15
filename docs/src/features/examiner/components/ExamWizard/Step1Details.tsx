import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { useExaminerStore } from '../../store/examinerStore';

const detailsSchema = z.object({
  title: z.string().min(5, 'Title must be at least 5 characters'),
  description: z.string().min(10, 'Description must be at least 10 characters'),
  duration_minutes: z.number().min(15, 'Minimum 15 minutes').max(300, 'Maximum 300 minutes'),
  pass_percentage: z.number().min(0).max(100),
});

type DetailsFormData = z.infer<typeof detailsSchema>;

const Step1Details = () => {
  const { currentDraft, updateDraftDetails, setStep } = useExaminerStore();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<DetailsFormData>({
    resolver: zodResolver(detailsSchema),
    defaultValues: {
      title: currentDraft.title,
      description: currentDraft.description,
      duration_minutes: currentDraft.duration_minutes,
      pass_percentage: currentDraft.pass_percentage,
    },
  });

  const onSubmit = (data: DetailsFormData) => {
    updateDraftDetails(data);
    setStep(2);
  };

  return (
    <div className="card p-8">
      <h2 className="text-2xl font-bold text-slate-900 mb-6">Exam Details</h2>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
        {/* Title */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Exam Title *
          </label>
          <input
            {...register('title')}
            type="text"
            className={`input-field ${errors.title ? 'border-rose-500' : ''}`}
            placeholder="e.g., Data Structures Final Exam"
          />
          {errors.title && (
            <p className="mt-1 text-sm text-rose-600">{errors.title.message}</p>
          )}
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-2">
            Description *
          </label>
          <textarea
            {...register('description')}
            rows={4}
            className={`input-field resize-none ${errors.description ? 'border-rose-500' : ''}`}
            placeholder="Provide a brief description of the exam..."
          />
          {errors.description && (
            <p className="mt-1 text-sm text-rose-600">{errors.description.message}</p>
          )}
        </div>

        {/* Duration & Pass Percentage */}
        <div className="grid grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Duration (minutes) *
            </label>
            <input
              {...register('duration_minutes', { valueAsNumber: true })}
              type="number"
              min="15"
              max="300"
              className={`input-field ${errors.duration_minutes ? 'border-rose-500' : ''}`}
              placeholder="60"
            />
            {errors.duration_minutes && (
              <p className="mt-1 text-sm text-rose-600">{errors.duration_minutes.message}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 mb-2">
              Pass Percentage *
            </label>
            <input
              {...register('pass_percentage', { valueAsNumber: true })}
              type="number"
              min="0"
              max="100"
              className={`input-field ${errors.pass_percentage ? 'border-rose-500' : ''}`}
              placeholder="40"
            />
            {errors.pass_percentage && (
              <p className="mt-1 text-sm text-rose-600">{errors.pass_percentage.message}</p>
            )}
          </div>
        </div>

        {/* Submit Button */}
        <div className="flex justify-end pt-4">
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            className="btn-primary flex items-center gap-2"
          >
            Next: Add Questions
            <ArrowRight className="w-5 h-5" />
          </motion.button>
        </div>
      </form>
    </div>
  );
};

export default Step1Details;