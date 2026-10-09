'use strict';

// World text is data: no HTML insertion, source evaluation, or generated URLs.
const $ = id => document.getElementById(id);
const state = { world: null, card: null, draft: null, detail: null, generation: 0, sending: false, uncertain: false };
const text = value => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = text(content);
  return node;
}
function notice(message, error = false) {
  $('notice').textContent = text(message);
  $('notice').classList.toggle('error', error);
  $('notice').hidden = !message;
}
async function api(path, body) {
  const options = { headers: { Accept: 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers['Content-Type'] = 'application/json';
    options.headers['X-Delvetalk-CSRF'] = state.world?.csrf || '';
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); }
  catch { throw new Error(`The portal returned an unreadable reply (${response.status}).`); }
  if (!response.ok) {
    const error = new Error(text(data.message || data.error) || `Request failed (${response.status}).`);
    error.code = data.error;
    error.httpStatus = response.status;
    throw error;
  }
  return data;
}
async function busy(button, label, work) {
  const before = button.textContent;
  button.disabled = true;
  button.textContent = label;
  try { await work(); }
  catch (error) { notice(error.message, true); }
  finally { button.disabled = false; button.textContent = before; }
}
async function copy(value, button) {
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(value);
    else {
      const area = element('textarea', 'copy-buffer');
      area.value = value;
      area.setAttribute('aria-label', 'Text to copy');
      document.body.append(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      if (!copied) throw new Error('Copy is unavailable. Select the command text to copy it.');
    }
    const prior = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { if (button.isConnected) button.textContent = prior; }, 1600);
  } catch (error) { notice(error.message, true); }
}
function renderObjects() {
  $('objects').replaceChildren();
  for (const object of state.world.objects || []) {
    const button = element('button', 'object-link');
    button.type = 'button';
    button.setAttribute('aria-current', String(object.id === state.card?.object));
    const symbol = element('span', 'object-symbol', '◇');
    symbol.setAttribute('aria-hidden', 'true');
    const label = element('span');
    label.append(element('strong', '', object.title || object.id));
    label.append(element('small', '', object.version == null ? 'Open object' : `Version ${text(object.version)}`));
    button.append(symbol, label);
    button.addEventListener('click', () => openObject(object.id, true));
    $('objects').append(button);
  }
  if (!$('objects').childElementCount) $('objects').append(element('p', 'muted', 'No objects here yet.'));
}
async function loadWorld() {
  const world = await api('/api/world');
  state.world = world;
  $('world-title').textContent = world.title || 'The workbench';
  $('mode').textContent = world.mode === 'local-interactive' ? 'Local world' : 'Read-only world';
  $('principal').textContent = world.principal ? `As ${world.principal}` : '';
  document.querySelector('.connection').classList.add('ready');
  $('footer-mode').textContent = world.mode === 'local-interactive'
    ? 'Every action begins as a draft.' : 'Explore, inspect and prepare a draft.';
  const assisted = world.interpretation === 'model-assisted';
  $('interpret-label').textContent = assisted ? 'Or say what you have in mind' : 'Or paste an action token';
  $('intent-text').placeholder = assisted ? 'Describe a next step…' : 'do CARD ACTION';
  $('interpret-help').textContent = assisted
    ? 'A suggestion is a draft. You decide whether to send it.'
    : 'Copied tokens become proposals here. You decide whether to send them.';
  renderObjects();
  return world;
}
function clearDraft() {
  state.draft = null;
  state.uncertain = false;
  $('draft-panel').hidden = true;
  $('draft-state').textContent = '';
  const url = new URL(location.href);
  url.searchParams.delete('draft');
  history.replaceState(null, '', url);
}
async function openObject(id, focus = false) {
  if (state.sending) return notice('Wait for the send result before replacing this reading.');
  const generation = ++state.generation;
  notice('');
  try {
    const card = await api(`/api/object?object=${encodeURIComponent(id)}&panel=main`);
    if (generation !== state.generation) return;
    state.card = card;
    state.detail = null;
    if (!state.uncertain) clearDraft();
    $('object-title').textContent = card.title || id;
    $('object-prose').textContent = text(card.prose);
    $('version').textContent = card.version == null ? '' : `v${text(card.version)}`;
    $('card-token').textContent = card.card;
    $('object-meta').hidden = false;
    $('inspect').hidden = false;
    $('inspect').open = false;
    $('detail-content').textContent = 'Opening…';
    $('copy-detail').disabled = true;
    $('detail-tabs').replaceChildren();
    $('interpret-form').hidden = false;
    $('intent-text').value = '';
    $('interpret-result').replaceChildren();
    renderActions(card);
    renderObjects();
    const url = new URL(location.href);
    url.searchParams.set('object', id);
    history.replaceState(null, '', url);
    document.title = `${card.title || id} · DelveTalk`;
    if (focus) $('object-card').focus({ preventScroll: true });
  } catch (error) { if (generation === state.generation) notice(error.message, true); }
}
function fieldInput(field, actionId, index) {
  const label = element('label', 'field-label');
  const id = `field-${actionId}-${index}`;
  label.htmlFor = id;
  const caption = element('span', '', field.label || field.name);
  if (field.required) caption.append(element('span', 'required', ' · required'));
  let input;
  if (field.type === 'enum') {
    input = element('select');
    const empty = element('option', '', 'Choose…');
    empty.value = '';
    input.append(empty);
    for (const [optionIndex, option] of (field.options || []).entries()) {
      const choice = element('option', '', option);
      choice.value = String(optionIndex);
      input.append(choice);
    }
  } else {
    input = element('input');
    input.type = field.type === 'bool' ? 'checkbox' : 'text';
    if (field.type === 'nat') {
      input.inputMode = 'numeric';
      input.pattern = '0|[1-9][0-9]*';
      const minimum = Number.isSafeInteger(field.minimum) ? field.minimum : 0;
      const maximum = Number.isSafeInteger(field.maximum) ? field.maximum : Number.MAX_SAFE_INTEGER;
      input.title = `A whole number from ${minimum} to ${maximum}`;
      input.placeholder = `${minimum}–${maximum}`;
    }
    if (field.placeholder) input.placeholder = field.placeholder;
  }
  input.id = id;
  input.name = field.name;
  input.required = Boolean(field.required) && (field.type === 'enum' || field.type === 'nat'
    || (field.type === 'string' && field.minLength > 0));
  input.dataset.fieldType = field.type;
  if (field.type === 'bool') label.append(input, caption);
  else label.append(caption, input);
  return { label, input, field };
}
function readFields(controls) {
  const fields = Object.create(null);
  for (const { field, input } of controls) {
    input.setCustomValidity('');
    if (field.type === 'bool') fields[field.name] = input.checked;
    else if (!input.value && !field.required) continue;
    else if (field.type === 'enum') {
      if (input.value === '') {
        input.setCustomValidity('Choose one of the offered values.');
        input.reportValidity();
        throw new Error('Choose a value in the action form.');
      }
      fields[field.name] = field.options[Number(input.value)];
    }
    else if (field.type === 'nat') {
      const value = Number(input.value);
      const minimum = Number.isSafeInteger(field.minimum) ? field.minimum : 0;
      const maximum = Number.isSafeInteger(field.maximum) ? field.maximum : Number.MAX_SAFE_INTEGER;
      if (!/^(0|[1-9][0-9]*)$/.test(input.value) || !Number.isSafeInteger(value) || value < minimum || value > maximum) {
        input.setCustomValidity(`Enter a whole number from ${minimum} to ${maximum}.`);
        input.reportValidity();
        throw new Error('Check the number in the action form.');
      }
      fields[field.name] = value;
    } else {
      if (field.type === 'string') {
        const length = [...input.value].length;
        if ((field.minLength != null && length < field.minLength) || (field.maxLength != null && length > field.maxLength)) {
          input.setCustomValidity(`Enter between ${field.minLength ?? 0} and ${field.maxLength ?? 'the permitted number of'} characters.`);
          input.reportValidity();
          throw new Error('Check the text length in the action form.');
        }
      }
      fields[field.name] = input.value;
    }
  }
  return fields;
}
function renderActions(card) {
  const actions = Array.isArray(card.actions) ? card.actions : [];
  $('actions').replaceChildren();
  $('actions-section').hidden = false;
  for (const [index, action] of actions.entries()) {
    const form = element('form', 'action');
    const top = element('div', 'action-top');
    const label = element('p', 'action-label', action.label || action.id);
    const submit = element('button', 'secondary', 'Prepare');
    submit.type = 'submit';
    const inspectOnly = action.inspectOnly === true || action.available === false;
    submit.disabled = inspectOnly;
    top.append(label, submit);
    form.append(top);
    if (action.description) form.append(element('p', 'action-description', action.description));
    if (action.observedAvailable === false)
      form.append(element('p', 'help', 'Its condition was false when this room was read. The world checks it again when you send.'));
    const controls = (action.fields || []).map((field, i) => fieldInput(field, index, i));
    if (controls.length) {
      const group = element('div', 'action-fields');
      controls.forEach(control => group.append(control.label));
      form.append(group);
    }
    if (inspectOnly) form.append(element('p', 'help', action.reason || 'Inspect this action’s contract for its required input.'));
    const tokenRow = element('div', 'action-token');
    const code = element('code', '', action.token || `do ${card.card} ${action.id}`);
    const copyButton = element('button', 'text-button', 'Copy token');
    copyButton.type = 'button';
    copyButton.addEventListener('click', async () => {
      try {
        const fields = readFields(controls);
        if (controls.length && !form.reportValidity()) return;
        const command = `do ${card.card} ${action.id}${Object.keys(fields).length ? ` ${JSON.stringify(fields)}` : ''}`;
        await copy(command, copyButton);
      } catch (error) { notice(error.message, true); }
    });
    tokenRow.append(code, copyButton);
    form.append(tokenRow);
    controls.forEach(({ input }) => input.addEventListener('input', () => input.setCustomValidity('')));
    form.addEventListener('submit', event => {
      event.preventDefault();
      busy(submit, 'Preparing…', async () => {
        const fields = readFields(controls);
        if (!form.reportValidity()) return;
        await prepare(card.card, action.id, fields);
      });
    });
    $('actions').append(form);
  }
  if (!actions.length) $('actions').append(element('p', 'muted', 'No actions are offered in this reading.'));
}
async function prepare(card, action, fields) {
  if (state.sending) throw new Error('Wait for the send result before preparing another action.');
  if (state.uncertain) throw new Error('Resolve or dismiss the uncertain draft before preparing another action.');
  const draft = await api('/api/prepare', { card, action, fields });
  if (state.card?.card !== card || state.sending || state.uncertain) return;
  showDraft(draft);
}
function showDraft(draft, restored = false) {
  state.draft = draft;
  state.uncertain = restored && draft.outcome == null;
  $('draft-summary').textContent = text(draft.summary);
  $('draft-target').textContent = draft.object
    ? `${text(draft.object)}${draft.version == null ? '' : ` · read at version ${text(draft.version)}`}` : '';
  $('draft-command').textContent = text(draft.token || draft.command || draft.draft);
  // Exact server JSON travels as a string: parsing numeric roots into JS Numbers
  // would lose precision even though their independently retained execution is exact.
  $('draft-wire').textContent = typeof draft.wireJson === 'string'
    ? draft.wireJson : JSON.stringify(draft.wire ?? draft, null, 2);
  document.querySelector('.draft-exact').open = false;
  const settled = draft.outcome === 'committed' || draft.outcome === 'refused';
  $('draft-state').textContent = settled ? `Retained outcome: ${draft.outcome}.` : '';
  const canSend = draft.canExecute === true && state.world.mode === 'local-interactive' && !settled;
  $('send-draft').disabled = !canSend;
  $('send-draft').textContent = settled ? 'Outcome retained' : restored ? 'Send / retry saved draft' : 'Send action';
  $('draft-help').textContent = settled
    ? 'This draft already has a retained receipt. Read the object again before preparing a new action.'
    : canSend
      ? restored
        ? 'Your saved draft is restored with the same intent. Sending it recovers its receipt or submits that exact action.'
        : 'This draft is tied to the object you just read. Send it when you’re ready.'
    : state.world.mode === 'read-only'
      ? 'This world is read-only. You can copy the proposal and inspect its exact details.'
      : 'This proposal cannot be sent here. You can copy it and inspect its exact details.';
  const url = new URL(location.href);
  url.searchParams.set('draft', draft.draft);
  history.replaceState(null, '', url);
  $('draft-panel').hidden = false;
  $('draft-panel').focus({ preventScroll: true });
  $('draft-panel').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
}
async function executeDraft() {
  const draft = state.draft;
  if (!draft || state.sending || !draft.canExecute || state.world.mode !== 'local-interactive') return;
  state.sending = true;
  $('send-draft').disabled = true;
  $('dismiss-draft').disabled = true;
  $('draft-state').textContent = 'Sending…';
  try {
    const result = await api('/api/execute', { draft: draft.draft });
    if (state.draft !== draft) return;
    if (result.kind === 'uncertain') {
      state.uncertain = true;
      $('draft-state').textContent = text(result.summary) || 'The reply is uncertain.';
      $('draft-help').textContent = 'Keep this draft. Retry the same action to recover its receipt; don’t prepare a replacement.';
      $('send-draft').textContent = 'Retry this draft';
      $('send-draft').disabled = false;
    } else if (result.kind === 'refused') {
      state.uncertain = false;
      draft.outcome = 'refused';
      $('draft-state').textContent = text(result.summary) || 'The action was refused.';
      $('draft-help').textContent = 'Read the object again before choosing a new action. A stale draft needs a fresh reading and a new intent.';
      notice(result.summary || 'The object did not accept this action.', true);
    } else if (result.kind === 'committed') {
      state.uncertain = false;
      draft.outcome = 'committed';
      $('draft-state').textContent = text(result.summary) || 'The action was committed.';
      $('draft-help').textContent = 'The world has kept a receipt. Read the object again to see what changed.';
      notice(result.summary || 'The action was committed. Read again to see the new state.');
      try { await loadWorld(); }
      catch { notice('The action committed, but the object shelf could not refresh. Its receipt is retained.'); }
    } else throw new Error('The portal returned an unknown action outcome.');
  } catch (error) {
    if (state.draft === draft) {
      state.uncertain = true;
      $('draft-state').textContent = error.message;
      $('draft-help').textContent = 'The outcome may be unknown. Keep this draft and retry it to recover the same receipt.';
      $('send-draft').textContent = 'Retry this draft';
      $('send-draft').disabled = false;
    }
  } finally {
    state.sending = false;
    $('dismiss-draft').disabled = false;
  }
}
async function loadDetail() {
  const card = state.card;
  if (!card || state.detail) return;
  try {
    const detail = await api(`/api/detail?card=${encodeURIComponent(card.card)}`);
    if (state.card !== card) return;
    state.detail = detail;
    const exact = detail.exact || {};
    const sections = ['source', 'state', 'law', 'root', 'history', 'runtime'].filter(key => Object.hasOwn(detail, key));
    sections.push('all');
    const exactRecord = '{\n' + Object.entries(detail).filter(([key]) => key !== 'exact')
      .map(([key, value]) => `  ${JSON.stringify(key)}: ${typeof exact[key] === 'string' ? exact[key] : JSON.stringify(value, null, 2)}`)
      .join(',\n') + '\n}';
    const show = key => {
      const value = key === 'all' ? detail : detail[key];
      $('detail-content').textContent = key === 'all' ? exactRecord
        : typeof exact[key] === 'string' ? exact[key]
          : JSON.stringify(value, null, 2);
      for (const button of $('detail-tabs').children) button.setAttribute('aria-pressed', String(button.dataset.key === key));
    };
    $('detail-tabs').replaceChildren();
    for (const key of sections) {
      const button = element('button', '', key === 'all' ? 'Exact record' : key[0].toUpperCase() + key.slice(1));
      button.type = 'button';
      button.dataset.key = key;
      button.addEventListener('click', () => show(key));
      $('detail-tabs').append(button);
    }
    show(sections[0]);
    $('copy-detail').disabled = false;
  } catch (error) { if (state.card === card) $('detail-content').textContent = error.message; }
}
$('inspect').addEventListener('toggle', () => { if ($('inspect').open) loadDetail(); });
$('refresh-world').addEventListener('click', () => busy($('refresh-world'), '…', async () => {
  await loadWorld();
  notice('The object shelf is up to date.');
}));
$('refresh-object').addEventListener('click', () => {
  if (state.sending) return notice('Wait for the send result before replacing this reading.');
  if (state.card) openObject(state.card.object);
});
$('dismiss-draft').addEventListener('click', clearDraft);
$('copy-draft').addEventListener('click', () => copy($('draft-command').textContent, $('copy-draft')));
$('copy-wire').addEventListener('click', () => copy($('draft-wire').textContent, $('copy-wire')));
$('copy-detail').addEventListener('click', () => copy($('detail-content').textContent, $('copy-detail')));
$('send-draft').addEventListener('click', executeDraft);
$('interpret-form').addEventListener('submit', event => {
  event.preventDefault();
  const card = state.card;
  if (!card) return;
  const button = event.submitter;
  busy(button, 'Thinking…', async () => {
    const proposal = await api('/api/interpret', { card: card.card, text: $('intent-text').value });
    if (state.card !== card) return;
    $('interpret-result').replaceChildren(element('p', '', proposal.message || proposal.summary || ''));
    if (proposal.status === 'proposed' && proposal.action) {
      await prepare(card.card, proposal.action, proposal.fields || {});
    }
  });
});
(async () => {
  try {
    const requestedParams = new URL(location.href).searchParams;
    const requested = requestedParams.get('object');
    const savedDraftId = requestedParams.get('draft');
    const world = await loadWorld();
    let savedDraft = null;
    let draftError = null;
    if (savedDraftId) {
      try { savedDraft = await api(`/api/draft?draft=${encodeURIComponent(savedDraftId)}`); }
      catch (error) { draftError = error; }
    }
    const id = (world.objects || []).find(object => object.id === requested)?.id
      || savedDraft?.object || world.defaultObject || world.objects?.[0]?.id;
    if (id) await openObject(id);
    if (savedDraft) showDraft(savedDraft, true);
    else if (draftError) notice(`The saved draft could not be opened: ${draftError.message}`, true);
  } catch (error) { notice(error.message, true); $('mode').textContent = 'World unavailable'; }
})();
