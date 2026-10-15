from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
urlpatterns=[
 path('educator/',views.educator,name='educator'),
 path('educator/learners/<int:pk>/',views.educator_learner,name='educator_learner'),
 path('educator/plans/<int:pk>/',views.review,name='review'),
 path('',views.home,name='home'),path('register/',views.register,name='register'),
 path('login/',auth_views.LoginView.as_view(template_name='core/login.html'),name='login'),
 path('logout/',auth_views.LogoutView.as_view(),name='logout'),
 path('dashboard/',views.dashboard,name='dashboard'),path('start/<int:course_id>/',views.start,name='start'),
 path('journey/<int:pk>/',views.journey_detail,name='journey'),path('lesson/<int:pk>/',views.lesson_detail,name='lesson'),
 path('checkin/<int:pk>/',views.checkin,name='checkin'),path('recovery/<int:pk>/',views.recovery,name='recovery'),
 path('share/<int:pk>/',views.share_toggle,name='share_toggle'),path('circle/<str:token>/',views.circle,name='circle'),
]
