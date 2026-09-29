import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'student' | 'examiner' | 'admin';
  is_verified?: boolean;
  created_at?: string;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  
  login: (user: User, token: string) => void;
  /** revokeOnServer (default true): also kill the token server-side. */
  logout: (opts?: { revokeOnServer?: boolean }) => void;
  updateUser: (user: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      
      login: (user, token) => {
        set({ 
          user, 
          token, 
          isAuthenticated: true 
        });
      },
      
      logout: (opts) => {
        // Server-side revocation (bumps the user's token_version, so this and
        // every other session's token stop working). Plain fetch, not the
        // axios instance: api.ts imports this store, and the 401 handler calls
        // logout({revokeOnServer: false}) — a dead token has nothing to revoke.
        const token = get().token;
        if (token && opts?.revokeOnServer !== false) {
          fetch('/api/v1/auth/logout', {
            method: 'POST',
            keepalive: true,
            headers: { Authorization: `Bearer ${token}` },
          }).catch(() => {});
        }
        set({ 
          user: null, 
          token: null, 
          isAuthenticated: false 
        });
      },
      
      updateUser: (updates) => {
        set((state) => ({
          user: state.user ? { ...state.user, ...updates } : null
        }));
      },
    }),
    {
      name: 'auth-storage',
    }
  )
);