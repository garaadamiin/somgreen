/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadBundle } from "@web/core/assets";
import { Component, onWillStart, useState, useRef, useEffect } from "@odoo/owl";

// Chart.js ships with Odoo's own web assets (web.chartjs_lib) and, like the
// core graph view (web/static/src/views/graph/graph_renderer.js), is loaded
// as a plain script that exposes a global `Chart` - there is no ES module to
// import it from.
/* global Chart */

const CHART_GREEN = "#1F9D55";
const CHART_GREEN_FILL = "rgba(31, 157, 85, 0.12)";

export class SomgreenDashboard extends Component {
    static template = "somgreen_dashboard.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.canvasRef = useRef("salesChart");
        this.chart = null;

        const today = new Date();
        const ninetyDaysAgo = new Date();
        ninetyDaysAgo.setDate(today.getDate() - 90);

        this.state = useState({
            loading: true,
            data: null,
            dateFrom: this._toDateString(ninetyDaysAgo),
            dateTo: this._toDateString(today),
        });

        onWillStart(async () => {
            await loadBundle("web.chartjs_lib");
            await this.fetchData();
        });

        useEffect(
            () => {
                this._renderChart();
            },
            () => [this.state.data, this.canvasRef.el]
        );
    }

    _toDateString(date) {
        return date.toISOString().split("T")[0];
    }

    get currentYear() {
        return new Date().getFullYear();
    }

    async fetchData() {
        this.state.loading = true;
        this.state.data = await this.orm.call("somgreen.dashboard", "get_dashboard_data", [], {
            date_from: this.state.dateFrom,
            date_to: this.state.dateTo,
        });
        this.state.loading = false;
    }

    async onFilterApply() {
        await this.fetchData();
    }

    async setQuickRange(range) {
        const today = new Date();
        const from = new Date();
        if (range === "90d") {
            from.setDate(today.getDate() - 90);
        } else if (range === "30d") {
            from.setDate(today.getDate() - 30);
        } else if (range === "year") {
            from.setMonth(0, 1);
        }
        this.state.dateFrom = this._toDateString(from);
        this.state.dateTo = this._toDateString(today);
        await this.fetchData();
    }

    _renderChart() {
        if (!this.canvasRef.el || !this.state.data) {
            return;
        }
        const { labels, values } = this.state.data.monthly_sales;
        if (this.chart) {
            this.chart.destroy();
        }
        this.chart = new Chart(this.canvasRef.el, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: "Monthly Sales",
                        data: values,
                        backgroundColor: CHART_GREEN_FILL,
                        borderColor: CHART_GREEN,
                        borderWidth: 2,
                        borderRadius: 6,
                        maxBarThickness: 36,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: "#eef1ef" },
                        ticks: { color: "#6b7268" },
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: "#6b7268" },
                    },
                },
            },
        });
    }
}

registry.category("actions").add("somgreen_dashboard", SomgreenDashboard);
