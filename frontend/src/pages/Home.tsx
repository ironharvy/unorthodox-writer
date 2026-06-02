import { Link } from 'react-router-dom';
import { isAuthenticated } from '../api/client';

export default function Home() {
  const authed = isAuthenticated();

  return (
    <div>
      <section className="home-hero">
        <h1>
          <span className="accent">Unorthodox</span> Writer
        </h1>
        <p className="tagline">Any idea. Any lyric. A story.</p>
        <p className="subtitle">
          Turn your fleeting thoughts, song lyrics, or wildest ideas into
          fully-formed stories. Powered by AI — from local models on the free
          tier to Claude and GPT on paid.
        </p>
        <Link
          to={authed ? '/create' : '/login'}
          className="btn btn-primary btn-lg"
        >
          Start Writing
        </Link>
      </section>

      <section className="home-tiers">
        <div className="tier-card">
          <h3>Free Tier</h3>
          <div className="price">$0</div>
          <ul>
            <li>3 stories per day</li>
            <li>Up to 500 words per story</li>
            <li>Local AI models</li>
            <li>Save up to 3 stories</li>
            <li>Basic genres & styles</li>
          </ul>
        </div>

        <div className="tier-card featured">
          <h3>Paid Tier</h3>
          <div className="price">$10/mo</div>
          <ul>
            <li>Unlimited stories</li>
            <li>Up to 5,000 words per story</li>
            <li>Claude & GPT models</li>
            <li>Unlimited saved stories</li>
            <li>All genres, styles & POVs</li>
            <li>Priority generation speed</li>
          </ul>
        </div>
      </section>
    </div>
  );
}
