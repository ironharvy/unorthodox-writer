interface TierBadgeProps {
  tier: 'free' | 'paid';
}

export default function TierBadge({ tier }: TierBadgeProps) {
  return (
    <span className={`tier-badge ${tier}`}>
      {tier === 'paid' ? '✦ Pro' : 'Free'}
    </span>
  );
}
