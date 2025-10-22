from django.contrib.auth.forms import UserCreationForm, UserChangeForm
from django.contrib.auth.mixins import UserPassesTestMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, DetailView, UpdateView, DeleteView
from django.contrib.auth.models import User


class SuperuserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser


class UserCreateView(SuperuserRequiredMixin, CreateView):
    model = User
    form_class = UserCreationForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:user_list')


class UserListView(SuperuserRequiredMixin, ListView):
    model = User
    template_name = 'users/user_list.html'


class UserDetailView(SuperuserRequiredMixin, DetailView):
    model = User
    template_name = 'users/user_detail.html'


class UserUpdateView(SuperuserRequiredMixin, UpdateView):
    model = User
    form_class = UserChangeForm
    template_name = 'users/user_form.html'
    success_url = reverse_lazy('users:user_list')


class UserDeleteView(SuperuserRequiredMixin, DeleteView):
    model = User
    template_name = 'users/user_confirm_delete.html'
    success_url = reverse_lazy('users:user_list')
