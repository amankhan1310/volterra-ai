import { Link, useLocation } from "react-router";
import { PageHeader } from "../components/layout/PageHeader";
import { Card } from "../components/ui/Card";

export function NotFoundPage() {
  const { pathname } = useLocation();
  return (
    <>
      <PageHeader
        title="Page not found"
        subtitle={`No page exists at ${pathname}.`}
      />
      <Card>
        <p>
          Use the sidebar or quick navigation, or go to the{" "}
          <Link to="/overview">Overview</Link>.
        </p>
      </Card>
    </>
  );
}
