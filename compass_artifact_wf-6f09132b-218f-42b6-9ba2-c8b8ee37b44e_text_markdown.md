# Taiga Docker Authentication Failure: The SECRET_KEY Disconnect

Your authentication issue—where POST /api/v1/auth returns 401 despite Django's authenticate() confirming user credentials in the shell—stems from **environment variable context mismatches between the manage.py shell and the running API container**. The most common culprit is **SECRET_KEY inconsistency**, but several Docker-specific configuration problems can cause this exact symptom pattern.

## The root cause: Context separation in Docker

When you run `./taiga-manage.sh shell` and successfully authenticate a user, you're operating in a different execution context than the running API. The shell command spawns a new container instance that may load environment variables differently than the persistent taiga-back service container. This creates a scenario where password hashing, token validation, or authentication backend configuration differs between contexts, causing authenticate() to return False in the API despite succeeding in the shell.

### Critical misconfigurations causing this issue

**SECRET_KEY inconsistency across containers** is the primary suspect. Taiga requires identical SECRET_KEY values in three containers: taiga-back, taiga-events, and taiga-protected. Password hashing in Django uses the SECRET_KEY as part of the HMAC validation for session tokens and can affect authentication flows. Check your docker-compose.yml:

```yaml
# These MUST be identical
x-environment:
  &default-back-environment
  TAIGA_SECRET_KEY: "your-secret-key"

taiga-events:
  environment:
    SECRET_KEY: "your-secret-key"  # Must match above

taiga-protected:
  environment:
    SECRET_KEY: "your-secret-key"  # Must match above
```

**Session cookie settings for HTTP deployments** block authentication when misconfigured. If running on localhost:9000 without HTTPS, Django's default secure cookie settings prevent authentication from working:

```yaml
# Required for HTTP (default is True for HTTPS)
SESSION_COOKIE_SECURE: "False"
CSRF_COOKIE_SECURE: "False"
```

The API authentication endpoint uses Django's session framework under the hood for certain validation steps, and secure-only cookies fail silently on HTTP connections.

**Database credential persistence in volumes** causes authentication failures after configuration changes. PostgreSQL initializes with credentials from the first docker-compose up, storing them persistently in the taiga-db-data volume. Changing POSTGRES_PASSWORD in .env afterward creates a split-brain scenario: new containers try to connect with new credentials, but the database expects old ones. The manage.py shell might successfully connect to the database while the API container fails.

### Taiga's authentication backend architecture

Taiga uses Django REST Framework's default authentication classes with **no custom authentication backend** in the standard configuration. The /api/v1/auth endpoint ultimately calls:

```python
user = authenticate(username=userid, password=password)
if user is None or not user.is_active:
    raise exceptions.AuthenticationFailed('Invalid user')
```

This means Django's standard authentication flow applies: it cycles through AUTHENTICATION_BACKENDS in order, attempting to authenticate with each. **Taiga doesn't explicitly define AUTHENTICATION_BACKENDS**, so Django uses its default: `django.contrib.auth.backends.ModelBackend`. This backend performs case-insensitive username/email matching and validates passwords against PBKDF2-SHA256 hashes stored in the database.

However, authentication plugins like LDAP, SAML, or OIDC add custom backends to this list. If you've configured any authentication plugins, they may require additional request context parameters that work in the API but aren't present in the shell. The LDAP backend, for example, performs network calls to bind against an LDAP server—these connections might succeed from one container but fail from another due to network configuration differences.

### Why set_password + save doesn't fix it

When you run `user.set_password('newpass'); user.save()` in the shell, you're hashing the password with the current container's configuration. But if the API container has a different SECRET_KEY or PASSWORD_HASHERS configuration, it will compute a different hash for the same password. Django's password hashing algorithm incorporates system-specific settings, and Docker environment variable isolation means two containers can have divergent configurations even when using the same docker-compose.yml.

Additionally, Django caches password hashers. If you've changed password hasher settings in docker-compose.yml but haven't fully restarted containers (docker-compose restart vs docker-compose down && docker-compose up), old hasher instances may persist in memory, causing new passwords to be hashed with outdated algorithms.

## Docker-specific authentication problems

**Volume persistence causing stale credentials**: The most reliable solution for password-related authentication failures is to purge volumes and reinitialize:

```bash
docker-compose down -v  # Destroys all volumes including database
# Verify .env file has correct passwords (alphanumeric only)
docker-compose up -d
# Wait for "Booted 3 service workers" in logs
docker-compose logs -f taiga-back
# Then create user
./taiga-manage.sh createsuperuser
```

Multiple GitHub issues (taigaio/taiga-docker#81, #90) confirm this is the most common fix for "password authentication failed" errors that persist despite credential resets.

**Special characters in passwords break authentication**: Docker Compose's environment variable parsing has issues with special characters in passwords. Community reports confirm that symbols like `!@#$%^&*` in POSTGRES_PASSWORD or RABBITMQ_PASS cause "very strange errors" during authentication. Stick to alphanumeric passwords in docker-compose.yml—you can use complex passwords for user accounts, but container-to-container authentication passwords should be simple.

**Case sensitivity in boolean environment variables**: This affects PUBLIC_REGISTER_ENABLED and similar settings. Backend expects `"True"` (capitalized) while frontend expects `"true"` (lowercase). While this doesn't directly cause authentication to fail, mismatched registration settings can prevent user creation or cause unexpected authentication backend behavior.

## Email vs username authentication and verified email requirements

Taiga **does not have a TAIGA_LOGIN_FORM_TYPE setting**—this is a common misconception. The authentication system accepts both username and email, performing case-insensitive matching automatically. The backend uses Django's authenticate() with the submitted credential as the username parameter, and Django's ModelBackend checks both the username and email fields.

**Email verification is NOT required for login by default**. The User model has a `verified_email` field, but authentication succeeds regardless of its value. Users created via createsuperuser or Django admin can log in immediately without email verification. However, if you've configured email domain restrictions with USER_EMAIL_ALLOWED_DOMAINS, authentication may fail silently for users with non-allowed email addresses.

## Common authentication backend order issues

When multiple authentication backends are configured (LDAP, SAML, GitHub OAuth), Django tries them sequentially. Each backend's authenticate() method can return None (user not found), a User object (success), or raise an exception. The first backend to return a User object wins.

**LDAP authentication requires additional context** that may not be present in shell testing. The LDAP backend:
1. Binds to LDAP with service account credentials
2. Searches for the user by username
3. Attempts to bind with user-provided credentials
4. Creates/updates local User record on success

If the LDAP server is accessible from taiga-back but not from the manage.py shell container (due to network policy differences), authentication will succeed in the API but fail in the shell—the opposite of your issue, but illustrating how backend-specific requirements cause context-dependent failures.

## Environment variable diagnostics and solutions

**Step 1: Verify environment variables in running container**

```bash
# Check what the API actually sees
docker-compose exec taiga-back env | grep -E 'SECRET|POSTGRES|TAIGA_SITES'

# Compare to manage.py shell context
docker-compose exec taiga-back bash -c 'echo $TAIGA_SECRET_KEY'
```

If these differ, you have a smoking gun. The docker-compose.yml might have hardcoded values that override .env file settings, or the manage.py script might be loading a different configuration file.

**Step 2: Test authentication directly against the database**

```bash
docker-compose exec taiga-db psql -U taiga -c "SELECT username, email, is_active, is_staff, is_superuser FROM users_user WHERE username='youruser';"
```

Verify the user actually exists with correct flags. Despite your assertion that is_active=True, database corruption or migration issues could have reset these flags.

**Step 3: Use Django shell to test in-container authentication**

```bash
docker-compose exec taiga-back python manage.py shell
```

```python
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
User = get_user_model()

# Test authentication exactly as API does
user = authenticate(username='youruser', password='yourpassword')
print(f"Result: {user}")  # Should be User object, not None

# If None, check password hash
user = User.objects.get(username='youruser')
print(f"Password hash: {user.password}")
print(f"Check password: {user.check_password('yourpassword')}")
```

If check_password() returns True but authenticate() returns None, you have an authentication backend configuration issue—an additional backend in the chain is blocking authentication.

**Step 4: Reset user credentials with verified flags**

```python
# In Django shell (docker-compose exec taiga-back python manage.py shell)
from django.contrib.auth import get_user_model
User = get_user_model()

user = User.objects.get(username='youruser')
user.is_active = True
user.is_staff = True
user.is_superuser = True
user.is_system = False  # Important: system users may have auth restrictions
user.set_password('newpassword')
user.save()
print(f"Updated: {user.username} - Active: {user.is_active}")
```

**Step 5: Verify SECRET_KEY consistency**

Create a test script in the taiga-back container:

```python
# test_secret.py
from django.conf import settings
print(f"SECRET_KEY: {settings.SECRET_KEY[:10]}...")  # Print first 10 chars
```

Run it in both contexts:
```bash
docker-compose exec taiga-back python -c "from django.conf import settings; settings.configure(); print(settings.SECRET_KEY[:10])"
./taiga-manage.sh shell -c "from django.conf import settings; print(settings.SECRET_KEY[:10])"
```

## Definitive fix procedure

Given your specific symptoms, follow this procedure:

**1. Complete configuration reset with verified consistency**

```bash
# Stop everything
docker-compose down -v

# Edit .env file - ensure these critical values:
SECRET_KEY=<generate-with: python -c 'import secrets; print(secrets.token_urlsafe(50))'>
POSTGRES_PASSWORD=<alphanumeric-only>
RABBITMQ_PASS=<alphanumeric-only>
SESSION_COOKIE_SECURE=False  # For HTTP on localhost
CSRF_COOKIE_SECURE=False     # For HTTP on localhost

# Verify docker-compose.yml has consistent SECRET_KEY references
# Ensure x-environment TAIGA_SECRET_KEY matches SECRET_KEY in taiga-events and taiga-protected

# Start fresh
docker-compose up -d

# Wait for backend initialization (critical)
docker-compose logs -f taiga-back
# Look for: "Booted 3 service workers"
```

**2. Create user with verified settings**

```bash
# Create superuser interactively
docker exec -it taiga-docker-taiga-back-1 python manage.py createsuperuser

# Verify creation succeeded
docker-compose exec taiga-back python manage.py shell
```

```python
from django.contrib.auth import get_user_model, authenticate
User = get_user_model()

user = User.objects.get(username='admin')
print(f"User: {user.username}")
print(f"Active: {user.is_active}")
print(f"Staff: {user.is_staff}")
print(f"Superuser: {user.is_superuser}")
print(f"Check password: {user.check_password('yourpassword')}")

# Test authentication
auth_user = authenticate(username='admin', password='yourpassword')
print(f"Authenticate result: {auth_user}")
```

**3. Test API endpoint directly**

```bash
curl -X POST http://localhost:9000/api/v1/auth \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"yourpassword","type":"normal"}'
```

If this returns a token, authentication works. If it returns 401, check nginx gateway logs:

```bash
docker-compose logs taiga-gateway | grep -i auth
```

## Known issues with specific setups

**Running behind reverse proxy** (nginx, Traefik) causes authentication failures when X-Forwarded headers aren't set correctly. The authentication endpoint validates request origin against TAIGA_SITES_DOMAIN, and missing headers cause domain mismatch:

```nginx
proxy_set_header Host $http_host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Scheme $scheme;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

**WebSocket authentication failures** affect token validation. If taiga-events isn't properly configured, initial token generation may succeed but subsequent requests fail. Verify:

```bash
docker-compose logs taiga-events | grep -i error
```

**POSTGRES_USER must never be changed** from "taiga". The docker-compose.yml hardcodes this in multiple places, and changing it breaks database initialization. Despite security instincts to customize this, leave it as "taiga"—the database runs on an internal Docker network anyway.

## Conclusion

Your authentication issue likely stems from **SECRET_KEY inconsistency between docker-compose environment contexts** or **stale database credentials in persistent volumes**. The most reliable fix is a complete teardown (docker-compose down -v), verification of environment variable consistency (especially SECRET_KEY and SESSION_COOKIE_SECURE), and fresh initialization. If authentication succeeds in the shell but fails in the API, focus on comparing environment variables between contexts using `docker-compose exec taiga-back env` versus what the manage.py script loads. The split-brain scenario where two execution contexts have divergent configurations is the signature pattern of this issue class.