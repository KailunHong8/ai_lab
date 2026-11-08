import WorkspaceTabs from "../components/WorkspaceTabs";
import ResearchLibrary from "./ResearchLibrary";
import Market from "./Market";
import Screener from "./Screener";

type View = "library" | "company" | "discover";

const TABS = [
  { to: "/research/library", label: "Library" },
  { to: "/research/company", label: "Company" },
  { to: "/research/discover", label: "Discover" },
];

// Research is one workspace with local views: saved evidence first, then company
// lookup and the screener as secondary discovery tools.
export default function Research({ view }: { view: View }) {
  return (
    <div>
      <WorkspaceTabs tabs={TABS} />
      {view === "library" && <ResearchLibrary />}
      {view === "company" && <Market />}
      {view === "discover" && <Screener />}
    </div>
  );
}
