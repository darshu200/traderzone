import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Sidebar from "@/components/Sidebar";
import LiveSignalsPage from "@/pages/LiveSignalsPage";
import TradeLogPage from "@/pages/TradeLogPage";
import AnalyticsPage from "@/pages/AnalyticsPage";
import BacktestPage from "@/pages/BacktestPage";
import SettingsPage from "@/pages/SettingsPage";
import CapitalPnLPage from "@/pages/CapitalPnLPage";
import { Toaster } from "@/components/ui/sonner";

function App() {
    return (
        <BrowserRouter>
            <div className="App flex min-h-screen" data-testid="app-root">
                <Sidebar />
                <main className="flex-1 flex flex-col min-w-0">
                    <Routes>
                        <Route path="/" element={<LiveSignalsPage />} />
                        <Route path="/log" element={<TradeLogPage />} />
                        <Route path="/analytics" element={<AnalyticsPage />} />
                        <Route path="/capital" element={<CapitalPnLPage />} />
                        <Route path="/backtest" element={<BacktestPage />} />
                        <Route path="/settings" element={<SettingsPage />} />
                    </Routes>
                </main>
            </div>
            <Toaster position="top-right" theme="dark" />
        </BrowserRouter>
    );
}

export default App;
