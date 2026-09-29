const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

// lane_chart.js reads the global ChartMath at load time (docs/plans/rf-profiles.md,
// section 4.1, decision 1), so it must be set before `require`, the same way a
// browser page loads chart_math.js before lane_chart.js.
global.ChartMath = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "chart_math.js")
);
const PulseqReport = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "lane_chart.js")
);
const {createMessageBus} = PulseqReport;

test("test_subscribe_replays_kept_messages_in_publication_order", () => {
  const bus = createMessageBus();
  bus.publish("t", {source: "a", v: 1});
  bus.publish("t", {source: "b", v: 2});
  const received = [];
  bus.subscribe("t", m => received.push(m));
  assert.deepEqual(received.map(m => [m.source, m.v]), [["a", 1], ["b", 2]]);
});

test("test_replacing_a_source_keeps_its_original_position_in_replay_order", () => {
  const bus = createMessageBus();
  bus.publish("t", {source: "a", v: 1});
  bus.publish("t", {source: "b", v: 1});
  // "a" publishes again: its kept message is replaced, but "a" published first, so
  // it must still come first on replay (the last message of each pair, in the order
  // the pairs were first published, not the order they were last updated).
  bus.publish("t", {source: "a", v: 2});
  const received = [];
  bus.subscribe("t", m => received.push(m));
  assert.deepEqual(received.map(m => [m.source, m.v]), [["a", 2], ["b", 1]]);
});

test("test_subscribe_with_replay_false_does_not_replay", () => {
  const bus = createMessageBus();
  bus.publish("t", {source: "a", v: 1});
  const received = [];
  bus.subscribe("t", m => received.push(m), {replay: false});
  assert.equal(received.length, 0);
  // A publish after subscribing still reaches it: only the replay of kept messages
  // is skipped, not future delivery.
  bus.publish("t", {source: "a", v: 2});
  assert.equal(received.length, 1);
  assert.equal(received[0].v, 2);
});

test("test_handlers_run_in_subscription_order", () => {
  const bus = createMessageBus();
  const order = [];
  bus.subscribe("t", () => order.push("first"), {replay: false});
  bus.subscribe("t", () => order.push("second"), {replay: false});
  bus.subscribe("t", () => order.push("third"), {replay: false});
  bus.publish("t", {source: "a"});
  assert.deepEqual(order, ["first", "second", "third"]);
});

test("test_a_throwing_handler_does_not_stop_the_others_or_the_publisher", () => {
  const errors = [];
  const bus = createMessageBus({
    onError: (error, topic, message) => errors.push({error, topic, message}),
  });
  const order = [];
  bus.subscribe("t", () => {
    order.push("first");
    throw new Error("boom");
  }, {replay: false});
  bus.subscribe("t", () => order.push("second"), {replay: false});

  assert.doesNotThrow(() => bus.publish("t", {source: "a"}));
  assert.deepEqual(order, ["first", "second"]);
  assert.equal(errors.length, 1);
  assert.equal(errors[0].error.message, "boom");
  assert.equal(errors[0].topic, "t");
  assert.equal(errors[0].message.source, "a");
});

test("test_publish_inside_a_handler_is_delivered_after_the_current_delivery_ends", () => {
  const bus = createMessageBus();
  const order = [];
  bus.subscribe("t", m => {
    order.push(`first:${m.v}`);
    // Published from inside a handler: must not be delivered until every handler of
    // this delivery (the message with v = 1) has run, including "second" below.
    if (m.v === 1) bus.publish("t", {source: "a", v: 2});
  }, {replay: false});
  bus.subscribe("t", m => order.push(`second:${m.v}`), {replay: false});

  bus.publish("t", {source: "a", v: 1});
  assert.deepEqual(order, ["first:1", "second:1", "first:2", "second:2"]);
});

test("test_unsubscribe_stops_future_deliveries", () => {
  const bus = createMessageBus();
  const received = [];
  const unsubscribe = bus.subscribe("t", m => received.push(m.v), {replay: false});
  bus.publish("t", {source: "a", v: 1});
  unsubscribe();
  bus.publish("t", {source: "a", v: 2});
  assert.deepEqual(received, [1]);
});

test("test_unsubscribe_during_a_delivery_stops_the_rest_of_that_delivery", () => {
  const bus = createMessageBus();
  const order = [];
  let unsubscribeSecond;
  bus.subscribe("t", () => {
    order.push("first");
    unsubscribeSecond();
  }, {replay: false});
  unsubscribeSecond = bus.subscribe("t", () => order.push("second"), {replay: false});
  bus.subscribe("t", () => order.push("third"), {replay: false});

  bus.publish("t", {source: "a"});
  // "second" is skipped for this delivery (unsubscribed by "first", which ran before
  // it); "third", subscribed before the delivery started, still runs.
  assert.deepEqual(order, ["first", "third"]);
});

test("test_unsubscribe_twice_does_nothing", () => {
  const bus = createMessageBus();
  const received = [];
  const other = [];
  const unsubscribe = bus.subscribe("t", m => received.push(m), {replay: false});
  bus.subscribe("t", m => other.push(m), {replay: false});

  unsubscribe();
  assert.doesNotThrow(() => unsubscribe());
  bus.publish("t", {source: "a"});
  assert.equal(received.length, 0);
  // A second unsubscribe call must not remove another handler by mistake (for
  // example through a stale array index).
  assert.equal(other.length, 1);
});

test("test_publish_freezes_the_message", () => {
  const bus = createMessageBus();
  const message = {source: "a", v: 1};
  bus.publish("t", message);
  assert.equal(Object.isFrozen(message), true);

  let received;
  bus.subscribe("t", m => { received = m; });
  assert.equal(Object.isFrozen(received), true);

  // A frozen object silently ignores an assignment outside strict mode, so the
  // value, not a thrown error, is the reliable check.
  message.v = 2;
  assert.equal(message.v, 1);
});

test("test_publish_throws_type_error_for_a_non_string_or_empty_topic", () => {
  const bus = createMessageBus();
  assert.throws(() => bus.publish("", {source: "a"}), TypeError);
  assert.throws(() => bus.publish(null, {source: "a"}), TypeError);
  assert.throws(() => bus.publish(42, {source: "a"}), TypeError);
});

test("test_publish_throws_type_error_for_a_message_without_a_string_source", () => {
  const bus = createMessageBus();
  assert.throws(() => bus.publish("t", {}), TypeError);
  assert.throws(() => bus.publish("t", {source: 42}), TypeError);
  assert.throws(() => bus.publish("t", null), TypeError);
  assert.throws(() => bus.publish("t", "not an object"), TypeError);
});

test("test_create_message_bus_returns_independent_buses", () => {
  const busA = createMessageBus();
  const busB = createMessageBus();
  const received = [];
  busB.subscribe("t", m => received.push(m), {replay: false});
  busA.publish("t", {source: "a"});
  assert.equal(received.length, 0);
});

test("test_watch_subscribers_calls_at_once_with_the_current_count", () => {
  const bus = createMessageBus();
  const counts = [];
  bus.watchSubscribers("t", n => counts.push(n));
  assert.deepEqual(counts, [0]);

  bus.subscribe("t", () => {}, {replay: false});
  bus.subscribe("t", () => {}, {replay: false});
  const later = [];
  bus.watchSubscribers("t", n => later.push(n));
  assert.deepEqual(later, [2]);
  // Only the subscribers of the watched topic count.
  bus.subscribe("u", () => {}, {replay: false});
  assert.deepEqual(counts, [0, 1, 2]);
});

test("test_watch_subscribers_calls_after_a_subscribe_and_after_an_unsubscribe", () => {
  const bus = createMessageBus();
  const counts = [];
  bus.watchSubscribers("t", n => counts.push(n));
  const first = bus.subscribe("t", () => {}, {replay: false});
  const second = bus.subscribe("t", () => {}, {replay: false});
  assert.deepEqual(counts, [0, 1, 2]);
  first();
  assert.deepEqual(counts, [0, 1, 2, 1]);
  // A second call of an unsubscribe function does not change the count.
  first();
  second();
  assert.deepEqual(counts, [0, 1, 2, 1, 0]);
});

test("test_a_stopped_watch_is_not_called_again", () => {
  const bus = createMessageBus();
  const stopped = [];
  const kept = [];
  const stop = bus.watchSubscribers("t", n => stopped.push(n));
  bus.watchSubscribers("t", n => kept.push(n));
  stop();
  assert.doesNotThrow(() => stop());
  bus.subscribe("t", () => {}, {replay: false});
  assert.deepEqual(stopped, [0]);
  assert.deepEqual(kept, [0, 1]);
});

// The only test that touches PulseqReport's own page-level bus (PulseqReport.publish
// and PulseqReport.subscribe): that singleton is shared by every test in this file's
// process (Node module caching), so this uses a topic name no other test publishes,
// to avoid replaying a kept message into an unrelated test.
test("test_pulseq_report_publish_and_subscribe_share_one_page_level_bus", () => {
  const received = [];
  PulseqReport.subscribe("__test_messages_js_only__", m => received.push(m), {replay: false});
  PulseqReport.publish("__test_messages_js_only__", {source: "a"});
  assert.equal(received.length, 1);
  assert.equal(received[0].source, "a");
});

test("test_bus_still_delivers_after_on_error_throws", () => {
  // An onError that throws propagates out of that publish (or subscribe), but must not
  // leave the bus marked as delivering: the next publish is delivered, not only queued.
  const bus = createMessageBus({
    onError: () => {
      throw new Error("onError failed");
    },
  });
  bus.subscribe("t", () => {
    throw new Error("handler failed");
  });
  assert.throws(() => bus.publish("t", {source: "a"}), /onError failed/);
  const received = [];
  bus.subscribe("u", m => received.push(m.source));
  bus.publish("u", {source: "b"});
  assert.deepEqual(received, ["b"]);

  // The same for a replay during subscribe.
  const bus2 = createMessageBus({
    onError: () => {
      throw new Error("onError failed");
    },
  });
  bus2.publish("t", {source: "a"});
  assert.throws(
    () => bus2.subscribe("t", () => {
      throw new Error("handler failed");
    }),
    /onError failed/
  );
  const received2 = [];
  bus2.subscribe("u", m => received2.push(m.source));
  bus2.publish("u", {source: "b"});
  assert.deepEqual(received2, ["b"]);
});
