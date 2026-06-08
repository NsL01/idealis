/** @odoo-module */

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, useState, onWillUpdateProps } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { AttachmentView } from "@mail/core/common/attachment_view";
import { useRecordObserver } from "@web/model/relational_model/utils";

export class CollaborativeInvoiceWidget extends Component {
    static template = "idealis_account.CollaborativeInvoiceWidget";
    static props = {
        threadId: { type: Number },
        threadModel: { type: String },
        record: { type: Object, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            collaborators: [],
            currencySymbol: "",
            invoiceTotal: 0,
            searchQuery: "",
            searchResults: [],
            selectedPartner: null,
            amount: 0,
            percentage: 0,
            showResults: false,
        });

        this.searchTimeout = null;

        // Load initial data if record observer won't trigger it
        if (!this.props.record) {
            this.loadData();
        } else {
            useRecordObserver((record) => {
                // We use the observer to dynamically update the widget's data when our data changes.
                // Example: A payment is recorded
                Object.keys(record.data).forEach((field) => record.data[field]);
                this.loadData();
            });
        }

        // Listen for props change
        onWillUpdateProps((nextProps) => {
            if (nextProps.threadId !== this.props.threadId) {
                this.loadData(nextProps.threadId);
            }
        });
    }

    async loadData(threadId = this.props.threadId) {
        if (!threadId) return;
        try {
            // Read move details (invoice total & currency)
            const moveData = await this.orm.read("account.move", [threadId], ["amount_total", "currency_id"]);
            if (moveData && moveData.length > 0) {
                const move = moveData[0];
                this.state.invoiceTotal = move.amount_total || 0;
                this.state.currencySymbol = move.currency_id ? move.currency_id[1] : "";
            }

            // Search read related collaborators
            const collaborators = await this.orm.searchRead(
                "account.move.collaborator",
                [["move_id", "=", threadId]],
                ["id", "contributor_id", "amount", "percentage", "amount_paid", "amount_remaining", "status"]
            );
            this.state.collaborators = collaborators;
        } catch (err) {
            console.error("Failed to load collaborative invoice details", err);
        }
    }

    get totalAssigned() {
        return this.state.collaborators.reduce((sum, c) => sum + (c.amount || 0), 0);
    }

    get totalPaid() {
        return this.state.collaborators.reduce((sum, c) => sum + (c.amount_paid || 0), 0);
    }

    get progressPercentage() {
        if (!this.state.invoiceTotal) return 0;
        return Math.min(100, Math.round((this.totalPaid / this.state.invoiceTotal) * 100));
    }

    get isSplitComplete() {
        return Math.abs(this.totalAssigned - this.state.invoiceTotal) < 0.01;
    }

    get splitDifference() {
        return this.state.invoiceTotal - this.totalAssigned;
    }

    formatNumber(val) {
        if (val === undefined || val === null) return "0";
        const floatVal = parseFloat(val);
        if (isNaN(floatVal)) return "0";
        if (floatVal % 1 === 0) {
            return Math.round(floatVal).toString();
        }
        return parseFloat(floatVal.toFixed(2)).toString();
    }

    formatCurrency(amount) {
        const symbol = this.state.currencySymbol || "€";
        return `${this.formatNumber(amount)} ${symbol}`;
    }

    formatPercentage(percentage) {
        return `${this.formatNumber(percentage * 100)}%`;
    }

    onPartnerInput(ev) {
        const query = ev.target.value;
        this.state.searchQuery = query;
        if (this.searchTimeout) {
            clearTimeout(this.searchTimeout);
        }

        if (query.trim().length < 2) {
            this.state.searchResults = [];
            this.state.showResults = false;
            return;
        }

        this.searchTimeout = setTimeout(async () => {
            try {
                const results = await this.orm.searchRead(
                    "res.partner",
                    [["name", "ilike", query]],
                    ["id", "name", "display_name"],
                    { limit: 8 }
                );
                this.state.searchResults = results;
                this.state.showResults = results.length > 0;
            } catch (err) {
                console.error("Error searching partners", err);
            }
        }, 250);
    }

    selectPartner(partner) {
        this.state.selectedPartner = { id: partner.id, name: partner.name };
        this.state.searchQuery = partner.name;
        this.state.showResults = false;
        this.state.searchResults = [];
    }

    clearPartnerSelection() {
        this.state.selectedPartner = null;
        this.state.searchQuery = "";
    }

    onAmountInput(ev) {
        const amount = parseFloat(ev.target.value) || 0;
        this.state.amount = amount;
        if (this.state.invoiceTotal) {
            this.state.percentage = parseFloat(((amount / this.state.invoiceTotal) * 100).toFixed(2));
        } else {
            this.state.percentage = 0;
        }
    }

    onPercentageInput(ev) {
        const percentage = parseFloat(ev.target.value) || 0;
        this.state.percentage = percentage;
        if (this.state.invoiceTotal) {
            this.state.amount = parseFloat(((percentage / 100) * this.state.invoiceTotal).toFixed(2));
        } else {
            this.state.amount = 0;
        }
    }

    async addContributor() {
        if (!this.state.selectedPartner) {
            this.notification.add("Please select a partner first.", { type: "warning" });
            return;
        }
        if (this.state.amount <= 0) {
            this.notification.add("Please enter a valid amount.", { type: "warning" });
            return;
        }

        const partnerId = this.state.selectedPartner.id;
        const exists = this.state.collaborators.some(c => c.contributor_id && c.contributor_id[0] === partnerId);
        if (exists) {
            this.notification.add("This contributor has already been added.", { type: "warning" });
            return;
        }

        try {
            await this.orm.create("account.move.collaborator", [{
                move_id: this.props.threadId,
                contributor_id: partnerId,
                amount: this.state.amount,
            }]);

            // Reset inputs and reload
            this.state.selectedPartner = null;
            this.state.searchQuery = "";
            this.state.amount = 0;
            this.state.percentage = 0;

            await this.loadData();
            this.safeReloadRecord();
        } catch (err) {
            console.error("Failed to add contributor", err);
            this.notification.add("Error adding contributor.", { type: "danger" });
        }
    }

    async removeContributor(collaboratorId) {
        try {
            await this.orm.unlink("account.move.collaborator", [collaboratorId]);
            await this.loadData();
            this.safeReloadRecord();
        } catch (err) {
            console.error("Failed to remove contributor", err);
            this.notification.add("Error removing contributor.", { type: "danger" });
        }
    }

    async sendReminder(collaboratorId) {
        try {
            await this.orm.call("account.move.collaborator", "action_send_reminder", [[collaboratorId]]);
            this.notification.add("Reminder sent successfully.", { type: "success" });
            await this.loadData();
            this.safeReloadRecord();
        } catch (err) {
            console.error("Failed to send reminder", err);
        }
    }

    async onCollaboratorAmountChange(colId, ev) {
        const amount = parseFloat(ev.target.value) || 0;
        if (amount <= 0) {
            this.notification.add("Please enter a valid amount.", { type: "warning" });
            return;
        }
        try {
            await this.orm.write("account.move.collaborator", [colId], { amount: amount });
            await this.loadData();
            this.safeReloadRecord();
        } catch (err) {
            console.error("Failed to update collaborator amount", err);
            this.notification.add("Error updating collaborator amount.", { type: "danger" });
        }
    }

    async onCollaboratorPercentageChange(colId, ev) {
        const percentageInput = parseFloat(ev.target.value) || 0;
        if (percentageInput <= 0 || percentageInput > 100) {
            this.notification.add("Please enter a valid percentage.", { type: "warning" });
            return;
        }
        const percentage = percentageInput / 100;
        try {
            await this.orm.write("account.move.collaborator", [colId], { percentage: percentage });
            await this.loadData();
            this.safeReloadRecord();
        } catch (err) {
            console.error("Failed to update collaborator percentage", err);
            this.notification.add("Error updating collaborator percentage.", { type: "danger" });
        }
    }

    safeReloadRecord() {
        let current = this;
        while (current) {
            if (current.props && current.props.record) {
                current.props.record.load().catch((err) => {
                    console.error("Failed to load record:", err);
                });
                break;
            }
            current = current.__owl__?.parent?.component;
        }
    }
}

// Patch Odoo's AttachmentView to mount our widget on posted customer invoices
patch(AttachmentView.prototype, {
    setup() {
        super.setup();
        this.orm = useService("orm");
        this.state.isCollaborativeInvoice = false;
        this.state.invoiceData = null;

        const updateInvoiceData = async (props) => {
            if (props.threadModel === "account.move" && props.threadId) {
                try {
                    const moveData = await this.orm.read("account.move", [props.threadId], ["state", "move_type"]);
                    if (moveData && moveData.length > 0) {
                        const move = moveData[0];
                        this.state.invoiceData = move;
                        this.state.isCollaborativeInvoice = (move.state === "posted" && ["out_invoice", "out_refund"].includes(move.move_type));
                    } else {
                        this.state.isCollaborativeInvoice = false;
                    }
                } catch (err) {
                    console.error("Failed to load invoice state for attachment preview", err);
                    this.state.isCollaborativeInvoice = false;
                }
            } else {
                this.state.isCollaborativeInvoice = false;
            }
        };

        // Initialize state
        updateInvoiceData(this.props);

        // Listen for props change (e.g. user toggles record)
        onWillUpdateProps(async (nextProps) => {
            if (nextProps.threadId !== this.props.threadId || nextProps.threadModel !== this.props.threadModel) {
                await updateInvoiceData(nextProps);
            }
        });
    },

    get isCollaborativeInvoice() {
        return this.state.isCollaborativeInvoice;
    }
});

// Register sub-component
AttachmentView.components = {
    ...AttachmentView.components,
    CollaborativeInvoiceWidget,
};

// Patch AttachmentView props to support optional record prop
if (Array.isArray(AttachmentView.props)) {
    if (!AttachmentView.props.includes("record?")) {
        AttachmentView.props.push("record?");
    }
} else if (AttachmentView.props) {
    AttachmentView.props.record = { type: Object, optional: true };
}

// Patch the form compiler to pass the record prop from FormRenderer to AttachmentView
const attachmentPreviewCompiler = registry.category("form_compilers").get("attachment_preview_compiler");
if (attachmentPreviewCompiler) {
    const originalFn = attachmentPreviewCompiler.fn;
    attachmentPreviewCompiler.fn = function (node, params) {
        const res = originalFn(node, params);
        const tElement = res.tagName === "T" ? res : res.querySelector("t");
        if (tElement) {
            tElement.setAttribute("record", "__comp__.props.record");
        }
        return res;
    };
}
