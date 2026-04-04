import { Plus, TrendingUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, Outlet } from "react-router";
import { Button } from "@/components/ui/button";
import { StockList, StockSearchModal } from "./components";

export default function HomeLayout() {
  const { t } = useTranslation();
  return (
    <div className="flex flex-1 flex-col gap-4 overflow-hidden bg-muted py-4 pr-4 pl-2">
      <div className="flex items-center justify-between">
        <h1 className="font-medium text-3xl">{t("home.welcome")}</h1>

        <Link to="/polymarket">
          <Button
            variant="outline"
            size="sm"
            className="flex items-center gap-2 border-green-500/40 text-green-600 hover:bg-green-500/10 hover:text-green-600 dark:text-green-400"
          >
            <TrendingUp size={15} />
            <span className="text-sm font-medium">Polymarket</span>
          </Button>
        </Link>
      </div>

      <div className="flex flex-1 gap-3 overflow-hidden">
        <main className="scroll-container flex-1 rounded-lg bg-card">
          <Outlet />
        </main>

        <aside className="flex w-72 flex-col overflow-hidden rounded-lg bg-card">
          <StockList />

          <StockSearchModal>
            <Button variant="secondary" className="mx-5 mb-6 font-bold text-sm">
              <Plus size={16} />
              {t("home.stock.add")}
            </Button>
          </StockSearchModal>
        </aside>
      </div>
    </div>
  );
}
