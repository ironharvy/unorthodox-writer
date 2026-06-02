import { useEffect, useState } from 'react';
import { getUserProfile, getUser } from '../api/client';
import TierBadge from '../components/TierBadge';
import type { User } from '../api/types';

export default function Account() {
  const cachedUser = getUser();
  const [user, setUser] = useState<User | null>(cachedUser);
  const [loading, setLoading] = useState(!cachedUser);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (cachedUser) return;
    getUserProfile()
      .then(setUser)
      .catch((err) => setError(err instanceof Error ? err.message : 'Failed to load profile'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="account-page">
        <p style={{ color: 'var(--text-muted)' }}>Loading account...</p>
      </div>
    );
  }

  if (error || !user) {
    return (
      <div className="account-page">
        <p style={{ color: 'var(--danger)' }}>{error || 'Could not load account'}</p>
      </div>
    );
  }

  const isFree = user.tier === 'free';

  return (
    <div className="account-page">
      <h1>Account</h1>

      <div className="account-tier">
        <span className="tier-label">{user.username}</span>
        <TierBadge tier={user.tier} />
      </div>

      <div className="account-stats">
        <div className="stat-card">
          <div className="stat-label">Stories Today</div>
          <div className="stat-value">
            {user.stories_today} / {user.daily_limit}
          </div>
          <div className="stat-limit">
            {isFree ? 'Free tier daily cap' : 'No hard limit'}
          </div>
        </div>

        <div className="stat-card">
          <div className="stat-label">Saved Stories</div>
          <div className="stat-value">
            {user.stories_saved} / {user.saved_limit}
          </div>
          <div className="stat-limit">
            {isFree ? 'Free tier limit' : 'Unlimited'}
          </div>
        </div>
      </div>

      {isFree && (
        <div className="upgrade-section">
          <h3>Want more?</h3>
          <p>
            Upgrade to Paid for unlimited stories, Claude & GPT models, 5,000
            words per story, and more.
          </p>
          <button className="btn btn-primary btn-lg" disabled>
            Upgrade to Pro — Coming Soon
          </button>
        </div>
      )}
    </div>
  );
}
