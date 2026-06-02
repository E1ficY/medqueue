from rest_framework import permissions

class IsAdminRole(permissions.BasePermission):
    """
    Custom permission to only allow users with the 'admin' role.
    """
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        if request.user.is_staff or request.user.is_superuser:
            return True
            
        try:
            return request.user.profile.role.lower() == 'admin'
        except Exception:
            return False


class IsResourceOwnerOrAdmin(permissions.BasePermission):
    """
    Custom permission to protect against OWASP A01 (BOLA).
    Allows access only if the user is the owner/creator of the resource or has an ADMIN role.
    """
    def has_permission(self, request, view):
        # Base permission check: user must be authenticated
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        # Admins always have access
        user = request.user
        is_admin = False
        if user.is_staff or user.is_superuser:
            is_admin = True
        else:
            try:
                is_admin = (user.profile.role.lower() == 'admin')
            except Exception:
                pass
        
        if is_admin:
            return True

        # Check ownership based on standard attribute names
        # Case 1: object is User itself
        if obj == user:
            return True
            
        # Case 2: object has a 'user' attribute (e.g., Appointment, UserProfile, etc.)
        if hasattr(obj, 'user') and getattr(obj, 'user') == user:
            return True
            
        # Case 3: object has an 'owner' attribute
        if hasattr(obj, 'owner') and getattr(obj, 'owner') == user:
            return True

        # Case 4: object is a profile linked to User
        if hasattr(obj, 'user_id') and getattr(obj, 'user_id') == user.id:
            return True

        return False
