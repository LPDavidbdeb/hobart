from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, UpdateView, DeleteView
from django.contrib.auth.models import User

# Note: The UserListView has been removed to avoid confusion.
# The main list view is now EmployeeListView in the 'employees' app.

class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class UserCreateView(SuperuserRequiredMixin, CreateView):
    model = User
    form_class = UserCreationForm
    template_name = 'users/user_form.html'
    # On success, redirect to the new, correct employee list
    success_url = reverse_lazy('employees:employee_list')


class UserDetailView(SuperuserRequiredMixin, DetailView):
    model = User
    template_name = 'users/user_detail.html'


class UserUpdateView(SuperuserRequiredMixin, UpdateView):
    model = User
    form_class = UserChangeForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('employees:employee_list')


class UserDeleteView(SuperuserRequiredMixin, DeleteView):
    model = User
    template_name = 'users/user_confirm_delete.html'
    success_url = reverse_lazy('employees:employee_list')
