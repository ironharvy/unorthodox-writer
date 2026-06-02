import { Link, Outlet, useLocation } from 'react-router-dom';
import { isAuthenticated, getUser, logout } from '../api/client';
import TierBadge from './TierBadge';

export default function Layout() {
  const location = useLocation();
  const authed = isAuthenticated();
  const user = getUser();

  const isActive = (path: string) => {
    if (path === '/') return location.pathname === '/';
    return location.pathname.startsWith(path);
  };

  return (
    <div className="layout">
      <nav className="navbar">
        <Link to="/" className="navbar-brand">
          Unorthodox Writer
        </Link>

        <ul className="navbar-links">
          <li>
            <Link to="/" className={isActive('/') && location.pathname === '/' ? 'active' : ''}>
              Home
            </Link>
          </li>
          {authed && (
            <>
              <li>
                <Link to="/create" className={isActive('/create') ? 'active' : ''}>
                  Create
                </Link>
              </li>
              <li>
                <Link to="/library" className={isActive('/library') ? 'active' : ''}>
                  Library
                </Link>
              </li>
              <li>
                <Link to="/account" className={isActive('/account') ? 'active' : ''}>
                  Account
                </Link>
              </li>
            </>
          )}
        </ul>

        <div className="navbar-right">
          {authed ? (
            <>
              <TierBadge tier={user?.tier || 'free'} />
              <button onClick={logout} className="btn btn-secondary btn-sm">
                Logout
              </button>
            </>
          ) : (
            <Link to="/login" className="btn btn-primary btn-sm">
              Sign In
            </Link>
          )}
        </div>
      </nav>

      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}
