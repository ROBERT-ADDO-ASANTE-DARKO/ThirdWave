import { TopBar } from "./TopBar";
import { Card, PlaceholderNotice } from "./ui";

// Stub for a nav destination that has a real backend route and Streamlit
// feature (see app.py's FEATURES dict / GOVT_DASHBOARD_PHASES.md) but
// hasn't been rebuilt in React yet. Keeps every sidebar link live so the
// shell is fully clickable while screens get built out one at a time.
export function Placeholder({
  title,
  subtitle,
  streamlitModule,
}: {
  title: string;
  subtitle: string;
  streamlitModule: string;
}) {
  return (
    <>
      <TopBar title={title} subtitle={subtitle} />
      <Card>
        <PlaceholderNotice>
          Not yet rebuilt in React. The working version of this feature lives in{" "}
          <code>streamlit_app/features/{streamlitModule}.py</code>.
        </PlaceholderNotice>
      </Card>
    </>
  );
}
