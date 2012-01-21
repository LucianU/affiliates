import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.http import base36_to_int
from django.utils.translation import get_language

import jingo
from basket import subscribe
from session_csrf import anonymous_csrf
from tower import ugettext_lazy as _lazy

from shared.utils import redirect
from shared.views import home
from users import forms
from users.models import RegisterProfile


log = logging.getLogger('a.users')


EDIT_PROFILE_SUCCESS = _lazy('Your profile was updated successfully!')


@anonymous_csrf
def login(request):
    form = forms.LoginForm(data=(request.POST or None))
    if request.method == 'POST':
        # TODO: Handle inactive users
        if form.is_valid():
            auth_login(request, form.get_user())

            # Set session to not expire on browser close
            if form.cleaned_data['remember_me']:
                request.session.set_expiry(settings.SESSION_REMEMBER_DURATION)

            return redirect('my_badges')

    return home(request, login_form=form)


@anonymous_csrf
def register(request):
    """Create a registration profile."""
    form = forms.RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        # Create a registration profile, which also emails
        # activation details
        profile = RegisterProfile.objects.create_profile(
            form.cleaned_data['display_name'], form.cleaned_data['email'],
            form.cleaned_data['registration_password'])

        # Sign the user up for mailing lists if they wanted
        if form.cleaned_data['email_subscribe']:
            try:
                subscribe(form.cleaned_data['email'],
                          settings.BASKET_NEWSLETTER,
                          lang=get_language())
            except Exception, err:
                log.warning(err)

        return jingo.render(request, 'users/register_done.html',
                            {'profile': profile})

    return home(request, register_form=form)


@anonymous_csrf
def activate(request, activation_key=None):
    """Activate a registration profile and create a user."""
    user = RegisterProfile.objects.activate_profile(activation_key)
    return jingo.render(request, 'users/activate_done.html',
                        {'activated_user': user})


@login_required
def edit_profile(request):
    """Edit an existing UserProfile."""
    if request.method == 'POST':
        data = request.POST.copy()

        # Remove password fields for BrowserID users
        if not request.user.has_usable_password():
            data['password'] = ''
            data['password2'] = ''
        form = forms.EditProfileForm(data, instance=request.user.get_profile())

        if form.is_valid():
            form.save()
            messages.success(request, unicode(EDIT_PROFILE_SUCCESS))
            return redirect('my_badges')
    else:
        form = forms.EditProfileForm(instance=request.user.get_profile())

    return jingo.render(request, 'users/edit_profile.html', {'form': form})


@anonymous_csrf
def send_password_reset(request):
    """View that displays the password reset form and sends the email out."""
    form = forms.PasswordResetForm(request.POST or None)
    if request.POST:
        is_valid = form.is_valid()
        if is_valid:
            sent = form.send()
        else:
            sent = False

        # Only reveal that an email exists if it was a valid email but
        # failed to send properly.
        if sent or not is_valid:
            return jingo.render(request,
                                'users/password_reset/send_complete.html')

    return jingo.render(request, 'users/password_reset/send_form.html',
                        {'form': form})


@anonymous_csrf
def password_reset(request, uidb36=None, token=None):
    """Validate password reset hash and process the password reset form."""

    try:
        uid_int = base36_to_int(uidb36)
    except ValueError:
        raise Http404

    user = get_object_or_404(User, id=uid_int)
    context = {}

    if default_token_generator.check_token(user, token):
        context['validlink'] = True
        if request.POST:
            form = forms.SetPasswordForm(user, request.POST)
            if form.is_valid():
                form.save()
                return jingo.render(request,
                                    'users/password_reset/complete.html')
        else:
            form = forms.SetPasswordForm(None)
    else:
        context['validlink'] = False
        form = None

    context['form'] = form
    return jingo.render(request, 'users/password_reset/confirm.html', context)
