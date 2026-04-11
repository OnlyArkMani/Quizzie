"""
Seed database with JEE Mains Physics Exam for demo
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, Option

def seed_physics_exam():
    db = SessionLocal()
    
    try:
        print("Seeding JEE Mains Physics Exam...")
        
        # Get examiner user to assign as creator
        examiner = db.query(User).filter(User.role == "examiner").first()
        if not examiner:
            print("No examiner found. Please run seed_data.py first to create users.")
            return

        exam = Exam(
            title="JEE Mains Physics Mock Test",
            description="A comprehensive 1-hour mock test covering class 11th and 12th physics topics for JEE Mains preparation.",
            duration_minutes=60,
            total_marks=60, # 15 questions * 4 marks
            pass_percentage=33,
            status="live",
            created_by=examiner.id
        )
        
        db.add(exam)
        db.commit()
        db.refresh(exam)
        
        print(f"Exam '{exam.title}' created with ID: {exam.id}")
        
        # Define 15 questions
        questions_data = [
            {
                "text": "A particle moves in a straight line with a constant acceleration. It changes its velocity from 10 m/s to 20 m/s while passing through a distance 135 m in t seconds. The value of t is:",
                "type": "single",
                "topic": "Kinematics",
                "options": [
                    {"text": "10", "correct": False},
                    {"text": "9", "correct": True},
                    {"text": "12", "correct": False},
                    {"text": "1.8", "correct": False}
                ]
            },
            {
                "text": "A block of mass 10 kg is kept on a rough inclined plane as shown in the figure. A force of 3 N is applied on the block. The coefficient of static friction between the plane and the block is 0.6. What should be the minimum value of force P, such that the block does not move downward? (take g = 10 m/s^2)",
                "type": "single",
                "topic": "Laws of Motion",
                "options": [
                    {"text": "32 N", "correct": True},
                    {"text": "18 N", "correct": False},
                    {"text": "23 N", "correct": False},
                    {"text": "25 N", "correct": False}
                ]
            },
            {
                "text": "A body of mass 1 kg begins to move under the action of a time dependent force F = (2ti + 3t^2j) N, where i and j are unit vectors along x and y axes. What power will be developed by the force at the time t?",
                "type": "single",
                "topic": "Work, Energy and Power",
                "options": [
                    {"text": "(2t^2 + 3t^3) W", "correct": False},
                    {"text": "(2t^3 + 3t^4) W", "correct": False},
                    {"text": "(2t^3 + 3t^5) W", "correct": True},
                    {"text": "(2t^2 + 4t^4) W", "correct": False}
                ]
            },
            {
                "text": "The moment of inertia of a solid cylinder of mass M, length 2R and radius R about an axis passing through its centre and perpendicular to its geometric axis is:",
                "type": "single",
                "topic": "Rotational Motion",
                "options": [
                    {"text": "MR^2 / 4", "correct": False},
                    {"text": "13 MR^2 / 12", "correct": False},
                    {"text": "11 MR^2 / 12", "correct": False},
                    {"text": "5 MR^2 / 6", "correct": True}
                ]
            },
            {
                "text": "The escape velocity from the Earth's surface is v. The escape velocity from the surface of another planet having a radius, four times that of Earth and same mass density is:",
                "type": "single",
                "topic": "Gravitation",
                "options": [
                    {"text": "4v", "correct": True},
                    {"text": "v", "correct": False},
                    {"text": "2v", "correct": False},
                    {"text": "v/2", "correct": False}
                ]
            },
            {
                "text": "An ideal gas undergoing expansion in vacuum shows:",
                "type": "multiple",
                "topic": "Thermodynamics",
                "options": [
                    {"text": "ΔU = 0", "correct": True},
                    {"text": "W = 0", "correct": True},
                    {"text": "q = 0", "correct": True},
                    {"text": "ΔT < 0", "correct": False}
                ]
            },
            {
                "text": "The RMS speed of oxygen molecules in a gas is v. If the temperature is doubled and the oxygen molecules dissociate into oxygen atoms, the RMS speed will become:",
                "type": "single",
                "topic": "Kinetic Theory of Gases",
                "options": [
                    {"text": "v", "correct": False},
                    {"text": "v * √2", "correct": False},
                    {"text": "2v", "correct": True},
                    {"text": "v / 2", "correct": False}
                ]
            },
            {
                "text": "In a simple harmonic oscillator, at the mean position:",
                "type": "multiple",
                "topic": "Oscillations and Waves",
                "options": [
                    {"text": "Velocity is maximum", "correct": True},
                    {"text": "Acceleration is zero", "correct": True},
                    {"text": "Kinetic energy is minimum", "correct": False},
                    {"text": "Potential energy is zero (assuming zero at equilibrium)", "correct": True}
                ]
            },
            {
                "text": "Two point charges A and B, having charges +Q and -Q respectively, are placed at certain distance apart and force acting between them is F. If 25% charge of A is transferred to B, then force between the charges becomes:",
                "type": "single",
                "topic": "Electrostatics",
                "options": [
                    {"text": "F", "correct": False},
                    {"text": "9F/16", "correct": True},
                    {"text": "16F/9", "correct": False},
                    {"text": "4F/3", "correct": False}
                ]
            },
            {
                "text": "A wire of resistance R is bent to form a complete circle. The resistance between two diametrically opposite points on the circle is:",
                "type": "single",
                "topic": "Current Electricity",
                "options": [
                    {"text": "R", "correct": False},
                    {"text": "R/2", "correct": False},
                    {"text": "R/4", "correct": True},
                    {"text": "2R", "correct": False}
                ]
            },
            {
                "text": "A charged particle moves through a magnetic field perpendicular to its direction. Then:",
                "type": "single",
                "topic": "Magnetic Effects of Current",
                "options": [
                    {"text": "The kinetic energy changes but momentum is constant", "correct": False},
                    {"text": "The momentum changes but kinetic energy is constant", "correct": True},
                    {"text": "Both momentum and kinetic energy of the particle are not constant", "correct": False},
                    {"text": "Both momentum and kinetic energy of the particle are constant", "correct": False}
                ]
            },
            {
                "text": "In an LCR circuit as frequency increases, what happens to the impedance?",
                "type": "single",
                "topic": "Electromagnetic Induction and AC",
                "options": [
                    {"text": "Increases continuously", "correct": False},
                    {"text": "Decreases continuously", "correct": False},
                    {"text": "First decreases, becomes minimum then increases", "correct": True},
                    {"text": "First increases, becomes maximum then decreases", "correct": False}
                ]
            },
            {
                "text": "In Young's double slit experiment, if the separation between coherent sources is halved and the distance of the screen from the coherent sources is doubled, then the fringe width becomes:",
                "type": "single",
                "topic": "Wave Optics",
                "options": [
                    {"text": "half", "correct": False},
                    {"text": "four times", "correct": True},
                    {"text": "one-fourth", "correct": False},
                    {"text": "double", "correct": False}
                ]
            },
            {
                "text": "According to Einstein's photoelectric equation, the plot of the kinetic energy of the emitted photo electrons from a metal Vs the frequency, of the incident radiation gives a straight line whose slope:",
                "type": "single",
                "topic": "Dual Nature of Matter",
                "options": [
                    {"text": "depends on the nature of the metal used", "correct": False},
                    {"text": "depends on the intensity of the radiation", "correct": False},
                    {"text": "is the same for all metals and independent of the intensity of radiation", "correct": True},
                    {"text": "is proportional to the work function of the metal", "correct": False}
                ]
            },
            {
                "text": "When a hydrogen atom emits a photon of energy 12.09 eV, its orbital angular momentum changes by (where h is Planck's constant):",
                "type": "single",
                "topic": "Atoms",
                "options": [
                    {"text": "h / π", "correct": True},
                    {"text": "2h / π", "correct": False},
                    {"text": "h / 2π", "correct": False},
                    {"text": "3h / 2π", "correct": False}
                ]
            }
        ]
        
        for i, q_data in enumerate(questions_data):
            question = Question(
                exam_id=exam.id,
                question_text=q_data["text"],
                question_type=q_data["type"],
                marks=4, # JEE Mains gives +4 for correct
                topic=q_data["topic"],
                display_order=i
            )
            db.add(question)
            db.flush()
            
            for j, opt_data in enumerate(q_data["options"]):
                option = Option(
                    question_id=question.id,
                    option_text=opt_data["text"],
                    is_correct=opt_data["correct"],
                    display_order=j
                )
                db.add(option)
                
        db.commit()
        
        print("15 Questions created successfully!")
        print("\n JEE Mains Physics Mock Test seeded successfully!")
        print(f"Exam ID: {exam.id}")
        
    except Exception as e:
        print(f" Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_physics_exam()
