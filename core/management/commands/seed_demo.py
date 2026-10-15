from django.core.management.base import BaseCommand
from core.models import Course,Milestone,Lesson,Question
from core.course_content import EXTRAS

DATA=[
 ('Getting Started with Python',[
 ('What is Python?', 'Python is a general-purpose programming language. A Python program contains instructions that a computer executes. The print() function displays output.', ('Which function displays text?','print()','input()','len()','A')),
 ('Variables and Values','Variables store references to values. For example, age = 20 assigns the integer 20 to age. Strings are written in quotation marks.',('Which is a valid variable assignment?','age == 20','age = 20','20 = age','B')),
 ('Data Types','Common types include int (whole number), float (decimal), str (text), and bool (True or False).',('Which value is a string?','42','True','"Hello"','C'))]),
 ('Control Flow',[
 ('Comparisons','Use == to test equality, > for greater than, and < for less than. Comparison expressions evaluate to True or False.',('Which operator checks equality?','=','==','!=','B')),
 ('If Statements','An if statement runs its indented body when the condition is True. An else block runs when it is False.',('When does an if block run?','When condition is True','Always','Never','A')),
 ('Loops','A for loop repeats an action over a sequence. For example, for n in range(3): print(n) prints 0, 1 and 2.',('What does range(3) produce?','1,2,3','0,1,2,3','0,1,2','C'))]),
 ('Functions',[
 ('Defining Functions','Use def to define a function. Example: def greet(name): return "Hi " + name. Call greet("Ada") to use it.',('Which keyword defines a function?','function','def','return','B')),
 ('Parameters and Returns','Parameters receive values passed to a function. return sends a result back to the caller.',('What sends a value back to the caller?','return','print','for','A'))]),
 ('Applied Python',[
 ('Lists','A list holds an ordered collection of items. Example: scores = [70, 80, 90]. Indexing begins at zero.',('What is [5, 6, 7][0]?','7','6','5','C')),
 ('Dictionaries','A dictionary maps keys to values. Example: person = {"name": "Ada"}. Use person["name"] to retrieve Ada.',('Which structure maps keys to values?','list','dictionary','tuple','B')),
 ('Putting It Together','Combine variables, loops, conditionals, and functions to solve a problem. Break the problem into small steps, test, then refine.',('What is a sensible first step in solving a programming problem?','Break it into steps','Write everything at once','Avoid testing','A'))]),
]
class Command(BaseCommand):
    help='Seed a small Python Basics course with four milestones and competency quizzes.'
    def handle(self,*args,**kwargs):
        course,_=Course.objects.get_or_create(title='Python Basics',defaults={'description':'Four milestones, eleven short lessons and practical knowledge checks.'})
        for i,(milestone_title,lessons) in enumerate(DATA,1):
            milestone,_=Milestone.objects.get_or_create(course=course,order=i,defaults={'title':milestone_title})
            for j,(title,content,q) in enumerate(lessons,1):
                example, extra, followup = EXTRAS[title]
                lesson,_=Lesson.objects.update_or_create(milestone=milestone,order=j,defaults={'title':title,'content':content + '\n\n' + example})
                Question.objects.get_or_create(lesson=lesson,prompt=q[0],defaults={'option_a':q[1],'option_b':q[2],'option_c':q[3],'correct':q[4]})
                for is_followup, questions in [(False, extra), (True, followup)]:
                    for question in questions:
                        Question.objects.update_or_create(lesson=lesson, prompt=question[0], is_followup=is_followup,
                            defaults={'option_a':question[1], 'option_b':question[2], 'option_c':question[3], 'correct':question[4]})
        self.stdout.write(self.style.SUCCESS('Python Basics demo course ready.'))
