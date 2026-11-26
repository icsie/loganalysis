const map = L.map("map", {
    worldCopyJump: true,
}).setView([20, 0], 2);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}).addTo(map);

const statusElement = document.getElementById("map-status");
const ipCountElement = document.getElementById("ip-count");
const attemptCountElement = document.getElementById("attempt-count");

function displayValue(value) {
    return value === null || value === undefined || value === ""
        ? "無資料"
        : String(value);
}

function addTooltipRow(container, label, value) {
    const row = document.createElement("div");
    row.className = "attack-tooltip-row";
    row.textContent = `${label}：${displayValue(value)}`;
    container.appendChild(row);
}

function createTooltip(record) {
    const content = document.createElement("div");
    content.className = "attack-tooltip-content";

    const title = document.createElement("div");
    title.className = "attack-tooltip-title";
    title.textContent = displayValue(record.addr);
    content.appendChild(title);

    addTooltipRow(content, "次數", record.n);
    addTooltipRow(
        content,
        "位置",
        [record.city_name, record.country_name].filter(Boolean).join(", "),
    );
    addTooltipRow(content, "ASN", record.asn);
    addTooltipRow(content, "網路", record.asn_network);
    addTooltipRow(content, "ASN 組織", record.asn_organization);
    addTooltipRow(content, "座標", `${record.latitude}, ${record.longitude}`);

    return content;
}

function setStatus(message) {
    statusElement.textContent = message;
}

async function loadAttackers() {
    try {
        const response = await fetch("/api/attackers", {
            headers: { Accept: "application/json" },
        });
        if (!response.ok) {
            throw new Error(`資料載入失敗（HTTP ${response.status}）`);
        }

        const records = await response.json();
        const locatedRecords = records.filter(
            (record) =>
                Number.isFinite(Number(record.latitude)) &&
                Number.isFinite(Number(record.longitude)) &&
                Number.isFinite(Number(record.n)),
        );
        const totalAttempts = records.reduce(
            (total, record) => total + (Number(record.n) || 0),
            0,
        );

        ipCountElement.textContent = records.length.toLocaleString();
        attemptCountElement.textContent = totalAttempts.toLocaleString();

        if (locatedRecords.length === 0) {
            setStatus(
                records.length === 0
                    ? "目前沒有可顯示的來源 IP。"
                    : `共 ${records.length} 個來源 IP，但沒有可用的座標。`,
            );
            return;
        }

        const maxCount = Math.max(
            ...locatedRecords.map((record) => Number(record.n)),
        );
        const markers = [];

        for (const record of locatedRecords) {
            const count = Number(record.n);
            const radius = Math.max(4, Math.sqrt(count / maxCount) * 22);
            const marker = L.circleMarker(
                [Number(record.latitude), Number(record.longitude)],
                {
                    radius,
                    color: "#991b1b",
                    weight: 1.5,
                    opacity: 0.9,
                    fillColor: "#ef4444",
                    fillOpacity: 0.56,
                },
            )
                .bindTooltip(createTooltip(record), {
                    direction: "top",
                    opacity: 0.98,
                    sticky: true,
                    className: "attack-tooltip",
                })
                .addTo(map);
            markers.push(marker);
        }

        if (markers.length === 1) {
            map.setView(markers[0].getLatLng(), 4);
        } else {
            map.fitBounds(L.featureGroup(markers).getBounds().pad(0.12), {
                maxZoom: 5,
            });
        }

        const unlocatedCount = records.length - locatedRecords.length;
        setStatus(
            unlocatedCount > 0
                ? `地圖顯示 ${locatedRecords.length} 個 IP；${unlocatedCount} 個 IP 沒有可用座標。`
                : `已顯示 ${locatedRecords.length} 個來源 IP。`,
        );
    } catch (error) {
        setStatus(
            error instanceof Error ? error.message : "無法載入地圖資料。",
        );
    }
}

loadAttackers();
