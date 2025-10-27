from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('faq/', views.FAQListView.as_view(), name='faq_list'),
]
