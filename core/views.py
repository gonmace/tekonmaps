"""Minimal views for the project."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render


@login_required
def home(request):
    """Home page view. Los anónimos se redirigen al login (LOGIN_URL)."""
    return render(request, 'home.html')
