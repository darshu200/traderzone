import { useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { updateSignal } from "@/lib/api";
import { toast } from "sonner";

export default function CloseTradeDialog({ signal, open, onOpenChange, onSaved }) {
    const [exitPrice, setExitPrice] = useState("");
    const [notes, setNotes] = useState("");
    const [busy, setBusy] = useState(false);

    if (!signal) return null;

    const submit = async (outcome) => {
        setBusy(true);
        try {
            const price = outcome === "BREAKEVEN" ? Number(exitPrice) || signal.entry
                : Number(exitPrice);
            if (outcome !== "BREAKEVEN" && !exitPrice) {
                toast.error("Enter exit price");
                setBusy(false); return;
            }
            await updateSignal(signal.id, { outcome, exit_price: price, notes });
            toast.success(`Marked ${outcome}`);
            onSaved && onSaved();
            onOpenChange(false);
            setExitPrice(""); setNotes("");
        } catch (e) {
            toast.error("Failed to update");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent data-testid="close-trade-dialog"
                style={{ background: "var(--ts-surface)", borderColor: "var(--ts-border)" }}>
                <DialogHeader>
                    <DialogTitle className="font-black">
                        Close Trade — {signal.instrument} · {signal.direction}
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 mt-2">
                    <div className="grid grid-cols-3 gap-2 text-sm">
                        <div>
                            <div className="ts-label">Entry</div>
                            <div className="font-mono">₹{signal.entry}</div>
                        </div>
                        <div>
                            <div className="ts-label">Stop</div>
                            <div className="font-mono">₹{signal.stoploss}</div>
                        </div>
                        <div>
                            <div className="ts-label">Target</div>
                            <div className="font-mono">₹{signal.target}</div>
                        </div>
                    </div>

                    <div>
                        <Label htmlFor="exit-price" className="ts-label">Exit Price</Label>
                        <Input
                            id="exit-price"
                            data-testid="close-trade-exit-price"
                            type="number" step="0.05"
                            value={exitPrice}
                            onChange={(e) => setExitPrice(e.target.value)}
                            className="mt-1 font-mono"
                            placeholder="e.g. 2450.30"
                        />
                    </div>
                    <div>
                        <Label htmlFor="notes" className="ts-label">Notes (optional)</Label>
                        <Textarea
                            id="notes"
                            data-testid="close-trade-notes"
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            className="mt-1"
                            rows={2}
                        />
                    </div>
                </div>

                <DialogFooter className="mt-4 gap-2">
                    <button data-testid="mark-lost-btn" disabled={busy}
                        onClick={() => submit("LOST")}
                        className="ts-btn-ghost" style={{ color: "var(--ts-short)" }}>
                        Mark Lost
                    </button>
                    <button data-testid="mark-be-btn" disabled={busy}
                        onClick={() => submit("BREAKEVEN")}
                        className="ts-btn-ghost">
                        Breakeven
                    </button>
                    <button data-testid="mark-won-btn" disabled={busy}
                        onClick={() => submit("WON")}
                        className="ts-btn-primary" style={{ background: "var(--ts-long)", color: "#000" }}>
                        Mark Won
                    </button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
