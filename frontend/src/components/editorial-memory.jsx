import { ArrowUpRight } from 'lucide-react';

export function EditorialMemory({ edition }) {
  const extractive = !!edition.takeaway_method;
  const title = extractive ? (edition.takeaways.length === 3 ? 'Three things I learned.' : 'From this edition.') : 'Three things to explore.';
  return <section className="takeaways" aria-label="Editorial memory">
    <div><span className="eyebrow">THE LAST WORD</span><h3>{title}</h3>
      <p>{extractive ? 'A short memory of this edition. Attributed source excerpts, not independently verified facts.' : 'Source headlines from this saved edition, linked to the original reporting.'}</p>
    </div>
    <ol>{edition.takeaways.map(item => <li key={item.article_id}><a href={item.url} target="_blank" rel="noopener noreferrer">{item.text}<ArrowUpRight size={15}/></a>
      <span>{item.source} · {item.kind === 'source_excerpt' ? 'Source excerpt' : 'Headline-level evidence'}</span>
    </li>)}</ol>
    {!edition.takeaways.length && <p>Not enough usable source text for editorial memory. No takeaways were invented.</p>}
  </section>;
}
