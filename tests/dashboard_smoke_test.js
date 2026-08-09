"use strict";

const fs = require("fs");
const vm = require("vm");

const elements = new Map();
const report = console.log;
console.log = () => {};
console.warn = () => {};

function makeClassList() {
    const values = new Set();
    return {
        add: (...names) => names.forEach(name => values.add(name)),
        remove: (...names) => names.forEach(name => values.delete(name)),
        toggle: (name, force) => {
            if (force === undefined ? !values.has(name) : force) values.add(name);
            else values.delete(name);
        },
        contains: name => values.has(name)
    };
}

function makeCanvasContext() {
    const gradient = { addColorStop() {} };
    return new Proxy({}, {
        get(target, property) {
            if (property in target) return target[property];
            if (property.startsWith("create") && property.endsWith("Gradient")) {
                return () => gradient;
            }
            return () => {};
        },
        set(target, property, value) {
            target[property] = value;
            return true;
        }
    });
}

function makeElement(id = "") {
    return {
        id,
        textContent: "",
        innerHTML: "",
        disabled: false,
        className: "",
        classList: makeClassList(),
        style: {},
        width: 640,
        height: 360,
        scrollTop: 0,
        scrollHeight: 0,
        children: [],
        listeners: {},
        addEventListener(event, callback) {
            this.listeners[event] = callback;
        },
        appendChild(child) {
            this.children.push(child);
        },
        getContext() {
            return makeCanvasContext();
        }
    };
}

function getElement(id) {
    if (!elements.has(id)) elements.set(id, makeElement(id));
    return elements.get(id);
}

let domReadyCallback = null;
global.document = {
    addEventListener(event, callback) {
        if (event === "DOMContentLoaded") domReadyCallback = callback;
    },
    getElementById: getElement,
    querySelectorAll(selector) {
        if (selector === ".btn-effector") {
            return ["btn-effect-ew", "btn-effect-laser", "btn-effect-kinetic"].map(getElement);
        }
        if (selector === ".btn-fusion") {
            return ["btn-eo-only", "btn-radar-only", "btn-fused-mode"].map(getElement);
        }
        return [];
    },
    createElement() {
        return makeElement();
    }
};

global.fetch = async () => ({
    ok: true,
    status: 200,
    json: async () => JSON.parse(fs.readFileSync("tests/fixtures/dashboard_identity_feed.json", "utf8"))
});
global.requestAnimationFrame = () => 0;
global.setInterval = () => 0;

const source = fs.readFileSync("app.js", "utf8");
vm.runInThisContext(source, { filename: "app.js" });

if (!domReadyCallback) throw new Error("DOMContentLoaded handler was not registered");
domReadyCallback();

setImmediate(() => {
    const assertions = [
        [getElement("data-mode-value").textContent === "REAL EO/IR OUTPUT", "real data mode"],
        [getElement("sensor-mode-value").textContent === "EO/IR ONLY", "EO-only sensor mode"],
        [getElement("coordinate-status").textContent === "NO GEOREFERENCE", "no georeferencing"],
        [getElement("radar-status").textContent === "NO RADAR DATA", "radar empty state"],
        [getElement("rf-status").textContent === "NO RF SENSOR DATA", "RF empty state"],
        [getElement("acoustic-status").textContent === "NO ACOUSTIC SENSOR DATA", "acoustic empty state"],
        [Number(getElement("confirmed-count").textContent) === 1, "confirmed identity count"],
        [Number(getElement("temporary-count").textContent) === 1, "temporary identity count"],
        [Number(getElement("internal-count").textContent) === 2, "immutable internal track count"],
        [Number(getElement("reid-count").textContent) === 1, "re-identification count"],
        [getElement("alias-result").textContent === "TEMP-1 -> ID-1", "identity alias result"],
        [getElement("resolver-mode").textContent.includes("DETERMINISTIC"), "honest resolver mode"],
        [getElement("sapient-json-display").textContent.includes("DetectionReport"), "SAPIENT-inspired inspector"]
    ];

    const failures = assertions.filter(([passed]) => !passed).map(([, name]) => name);
    if (failures.length > 0) {
        throw new Error(`Dashboard smoke test failed: ${failures.join(", ")}`);
    }
    report(`PASS: ${assertions.length} dashboard identity and capability assertions`);
});
