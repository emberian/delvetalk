'use strict';

// World text is data: no HTML insertion, source evaluation, or generated URLs.
const $ = id => document.getElementById(id);
const state = { world: null, card: null, draft: null, preparation: null, preparationGeneration: 0, detail: null, generation: 0, routeGeneration: 0, location: location.href, sending: false, uncertain: false };
const authoring = { draft: null, pending: false, preparing: false, uncertain: false, source: null, sourceText: null, rawFiles: {}, status: null };
const text = value => typeof value === 'string' ? value : value == null ? '' : JSON.stringify(value);
function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = text(content);
  return node;
}
const preparationAnswers = element('div', 'preparation-answers');
$('draft-panel').append(preparationAnswers);
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
    label.append(element('small', '', object.title && object.title !== object.id ? object.id
      : object.version == null ? 'Open object' : `Version ${text(object.version)}`));
    button.append(symbol, label);
    button.addEventListener('click', () => openObject(object.id, true, 'main', 'push'));
    $('objects').append(button);
  }
  if (!$('objects').childElementCount) $('objects').append(element('p', 'muted', 'No objects here yet.'));
}
async function loadWorld() {
  const world = await api('/api/world');
  state.world = world;
  $('world-title').textContent = world.title || 'The workbench';
  const preview = world.mode === 'public-preview';
  $('mode').textContent = preview ? 'Public preview' : world.mode === 'local-interactive' ? 'Local world' : 'Read-only world';
  $('principal').textContent = world.principal ? `As ${world.principal}` : '';
  document.querySelector('.connection').classList.add('ready');
  $('footer-mode').textContent = preview ? 'Temporary previews · copy what you want to keep.' : world.mode === 'local-interactive'
    ? 'Every action begins as a draft.' : 'Explore, inspect and prepare a draft.';
  $('preview-scope').hidden = !preview;
  const minutes = Math.ceil((world.custody?.ttlSeconds || 900) / 60);
  $('preview-scope').textContent = `Explore this world and preview its offered actions. Nothing you do here changes the world or posts to town. Previews last up to ${minutes} minutes; copy a summary to keep your idea. Exact request data is available separately.`;
  $('repository-export').hidden = preview || world.capabilities?.repository === false;
  const assisted = world.interpretation === 'model-assisted';
  $('interpret-label').textContent = assisted ? 'Or say what you have in mind' : 'Or paste an action token';
  $('intent-text').placeholder = assisted ? 'Describe a next step…' : 'do CARD ACTION';
  $('interpret-form').hidden = preview;
  $('interpret-help').textContent = assisted
    ? 'A suggestion is a draft. You decide whether to send it.'
    : 'Copied tokens become proposals here. You decide whether to send them.';
  renderObjects();
  configureAuthoring(world.authoring);
  return world;
}
function clearRepositoryRecord() {
  $('repository-record').hidden = true;
  $('repository-json').textContent = '';
  $('repository-status').textContent = '';
}
function writeLocation(url, push = false) {
  history[push ? 'pushState' : 'replaceState'](null, '', url);
  state.location = String(url);
}
function clearDraft(updateUrl = true) {
  if (updateUrl) ++state.preparationGeneration;
  state.draft = null;
  state.preparation = null;
  preparationAnswers.replaceChildren();
  state.uncertain = false;
  clearRepositoryRecord();
  $('draft-panel').hidden = true;
  $('draft-state').textContent = '';
  if (!updateUrl) return;
  const url = new URL(location.href);
  url.searchParams.delete('draft');
  url.searchParams.delete('preparation');
  writeLocation(url);
}
async function openObject(id, focus = false, panel = 'main', navigation = 'replace', childSelection = null, retainedCard = null) {
  if (state.sending) return notice('Wait for the send result before replacing this reading.');
  const generation = ++state.generation;
  ++state.routeGeneration;
  notice('');
  try {
    let card;
    if (retainedCard) {
      card = await api(`/api/card?card=${encodeURIComponent(retainedCard)}`);
      id = card.object;
    } else if (childSelection) {
      const result = await api(`/api/child?card=${encodeURIComponent(childSelection.card)}&key=${encodeURIComponent(childSelection.key)}`);
      if (result.status !== 'opened') throw new Error(result.message || 'This child is unavailable.');
      card = result.card;
      id = card.object;
    } else card = await api(`/api/object?object=${encodeURIComponent(id)}&panel=${encodeURIComponent(panel)}`);
    if (generation !== state.generation || state.sending || authoring.pending) return;
    state.card = card;
    state.detail = null;
    if (!state.uncertain) clearDraft(false);
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
    $('copy-reference').hidden = !card.objectRef;
    $('reference-status').textContent = text(card.referenceStatus);
    $('reference-status').hidden = !card.referenceStatus;
    $('unsupported-status').textContent = text(card.unsupported);
    $('unsupported-status').hidden = !card.unsupported;
    $('interpret-form').hidden = state.world.mode === 'public-preview';
    $('intent-text').value = '';
    $('interpret-result').replaceChildren();
    renderPanels(card);
    renderActions(card);
    if (card.panel === 'main') {
      const listed = state.world.objects.find(object => object.id === id);
      if (listed && card.title) listed.title = card.title;
    }
    renderViewChildren(card);
    $('object-children').replaceChildren();
    $('object-children').hidden = true;
    renderObjects();
    const url = new URL(location.href);
    url.searchParams.set('object', id);
    if (card.panel && card.panel !== 'main') url.searchParams.set('panel', card.panel);
    else url.searchParams.delete('panel');
    if (state.uncertain && state.draft) url.searchParams.set('draft', state.draft.draft);
    else url.searchParams.delete('draft');
    url.searchParams.delete('preparation');
    writeLocation(url, navigation === 'push');
    document.title = `${card.title || id} · DelveTalk`;
    if (focus) $('object-card').focus({ preventScroll: true });
    return true;
  } catch (error) {
    if (generation === state.generation) notice(childSelection
      ? `Unavailable: ${childSelection.label}. ${error.message}` : error.message, true);
  }
}
function renderPanels(card) {
  const nav = $('object-panels');
  nav.replaceChildren();
  const panels = card.panels || [{ id: 'main', label: 'Overview' }];
  nav.hidden = panels.length < 2;
  for (const panel of panels) {
    const button = element('button', 'panel-link', panel.label);
    button.type = 'button';
    button.setAttribute('aria-current', String(panel.id === (card.panel || 'main')));
    button.addEventListener('click', () => openObject(card.object, false, panel.id, 'push'));
    nav.append(button);
  }
  $('panel-warning').textContent = card.panelWarning || '';
  $('panel-warning').hidden = !card.panelWarning;
}
function fieldInput(field, actionId, index, partial = false) {
  const label = element('label', 'field-label');
  const id = `field-${actionId}-${index}`;
  label.htmlFor = id;
  const caption = element('span', '', field.label || field.name);
  if (field.required && !partial) caption.append(element('span', 'required', ' · required'));
  let input;
  if (field.type === 'enum' || (field.type === 'bool' && partial)) {
    input = element('select');
    const empty = element('option', '', 'Choose…');
    empty.value = '';
    input.append(empty);
    for (const [optionIndex, option] of (field.type === 'bool' ? ['Yes', 'No'] : field.options || []).entries()) {
      const choice = element('option', '', option);
      choice.value = field.type === 'bool' ? String(optionIndex === 0) : String(optionIndex);
      input.append(choice);
    }
  } else {
    const longText = field.type === 'string' && field.maxLength > 256;
    input = element(longText ? 'textarea' : 'input');
    if (longText) input.rows = 6;
    else input.type = field.type === 'bool' ? 'checkbox' : 'text';
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
  input.required = !partial && Boolean(field.required) && (field.type === 'enum' || field.type === 'nat'
    || (field.type === 'string' && field.minLength > 0));
  input.dataset.fieldType = field.type;
  if (field.type === 'bool' && !partial) label.append(input, caption);
  else label.append(caption, input);
  if (Object.hasOwn(field, 'example')) {
    // An authored example is guidance, never a default or a bound input.
    const example = field.example === '' ? '""' : text(field.example);
    if (field.type === 'string' || field.type === 'nat') input.placeholder = example;
    const hint = element('span', 'help', `Example: ${example}`);
    hint.id = `${id}-example`;
    input.setAttribute('aria-describedby', hint.id);
    label.append(hint);
  }
  return { label, input, field, partial };
}
function readFields(controls) {
  const fields = Object.create(null);
  for (const { field, input, partial } of controls) {
    input.setCustomValidity('');
    if (partial && input.value === '') continue;
    if (field.type === 'bool') {
      if (partial && !['true', 'false'].includes(input.value)) throw new Error('Choose Yes or No.');
      fields[field.name] = partial ? input.value === 'true' : input.checked;
    }
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
    const submit = element('button', 'secondary', state.world?.mode === 'public-preview' ? 'Preview' : 'Prepare');
    submit.type = 'submit';
    const inspectOnly = action.inspectOnly === true || action.available === false;
    submit.disabled = inspectOnly;
    top.append(label, submit);
    form.append(top);
    if (action.description) form.append(element('p', 'action-description', action.description));
    if (action.children?.length) {
      const preview = element('p', 'help');
      preview.textContent = `Creates new objects from ${action.children.map(child => child.value ?? child.field).join(', ')}. Each name must still be absent when the world admits the action.`;
      form.append(preview);
    }
    if (action.observedAvailable === false)
      form.append(element('p', 'help', 'Its condition was false when this room was read. The world checks it again when you send.'));
    const controls = (action.fields || []).map((field, i) => fieldInput(field, index, i, action.preparation === true));
    if (action.preparation) form.append(element('p', 'help', 'Start with what you know. The object can ask for more before proposing an action.'));
    for (const control of controls) {
      if (action.children?.some(child => child.field === control.field.name)) {
        control.input.pattern = '[A-Za-z0-9_-]{1,64}';
        control.input.title = 'A new child name using letters, digits, underscores or hyphens';
      }
    }
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
    if (state.world?.mode !== 'public-preview') form.append(tokenRow);
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
  if (authoring.pending || authoring.preparing || authoring.uncertain) throw new Error('Finish or resolve the source desk work before preparing another action.');
  const generation = ++state.preparationGeneration;
  const route = state.routeGeneration;
  const draft = await api('/api/prepare', { card, action, fields });
  if (generation !== state.preparationGeneration || route !== state.routeGeneration || state.card?.card !== card
      || state.sending || state.uncertain || authoring.pending || authoring.preparing || authoring.uncertain) return;
  if (draft.format === 'delvetalk-portal-preparation-v1') showPreparation(draft);
  else showDraft(draft);
}
function showPreparation(result) {
  state.draft = null;
  state.preparation = result;
  state.uncertain = false;
  clearRepositoryRecord();
  preparationAnswers.replaceChildren();
  const question = result.outcome.kind === 'question';
  $('draft-title').textContent = question ? 'A question from this object' : 'Preparation declined';
  $('draft-summary').textContent = text(result.outcome.message);
  $('draft-fields').replaceChildren();
  $('draft-target').textContent = `${text(result.object)} · read at version ${text(result.version)}`;
  for (const id of ['draft-absence', 'draft-command-row', 'preview-copy', 'send-draft', 'repository-export']) $(id).hidden = true;
  $('send-draft').disabled = true;
  $('draft-wire').textContent = '';
  document.querySelector('.draft-exact').hidden = true;
  $('draft-state').textContent = '';
  $('draft-help').textContent = 'Nothing has been submitted. These answers belong to the captured reading.';
  const needs = Array.isArray(result.outcome.needs) ? [...new Set(result.outcome.needs.filter(name => typeof name === 'string'))] : [];
  if (question && needs.length) {
    const action = state.card?.actions?.find(item => item.id === result.action);
    const form = element('form', 'action');
    const controls = needs.map((name, index) => {
      const field = action?.fields?.find(item => item.name === name)
        || { name, label: name, type: 'string', minLength: 0, maxLength: 65536 };
      const control = fieldInput(field, 'answer', index, true);
      if (Object.hasOwn(result.fields || {}, name)) {
        const value = result.fields[name];
        control.input.value = field.type === 'enum' ? String(field.options.indexOf(value)) : text(value);
      }
      form.append(control.label);
      return control;
    });
    const submit = element('button', 'secondary', 'Continue');
    submit.type = 'submit';
    form.append(submit);
    form.addEventListener('submit', event => {
      event.preventDefault();
      busy(submit, 'Preparing…', async () => {
        const answers = Object.assign(Object.create(null), result.fields || {}, readFields(controls));
        if (!form.reportValidity()) return;
        await prepare(result.card, result.action, answers);
      });
    });
    preparationAnswers.append(form);
  }
  const url = new URL(location.href);
  url.searchParams.delete('draft');
  url.searchParams.set('preparation', result.preparation);
  writeLocation(url);
  $('draft-panel').hidden = false;
  $('draft-panel').focus({ preventScroll: true });
}
function showDraft(draft, restored = false) {
  state.draft = draft;
  state.preparation = null;
  preparationAnswers.replaceChildren();
  document.querySelector('.draft-exact').hidden = false;
  $('repository-export').hidden = state.world.mode === 'public-preview' || state.world.capabilities?.repository === false;
  clearRepositoryRecord();
  state.uncertain = restored && draft.outcome == null && state.world.mode !== 'public-preview';
  const preview = state.world.mode === 'public-preview';
  $('draft-title').textContent = preview ? 'Your action preview' : 'A proposed action';
  $('draft-summary').textContent = text(draft.summary);
  $('draft-fields').replaceChildren();
  for (const [name, value] of Object.entries(draft.fields || {})) {
    $('draft-fields').append(element('dt', '', name), element('dd', '', text(value)));
  }
  $('preview-copy').hidden = !preview;
  $('draft-command-row').hidden = preview;
  $('send-draft').hidden = preview;
  $('draft-target').textContent = draft.reads?.length
    ? `Captured together: ${draft.reads.map(read => `${text(read.object)} · ${read.version == null ? "captured root" : `version ${text(read.version)}`}`).join('; ')}. All steps commit together.`
    : draft.object ? `${text(draft.object)}${draft.version == null ? '' : ` · read at version ${text(draft.version)}`}` : '';
  $('draft-absence').hidden = !draft.absence?.length;
  $('draft-absence').textContent = draft.absence?.length ? `Creates: ${draft.absence.join(', ')}. These object names must still be absent.` : '';
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
  $('draft-help').textContent = state.world.mode === 'public-preview'
    ? 'This is an unsent preview, not a town reply. Copy a summary to keep your idea. The exact request is optional technical detail; sending requires an authenticated receiving route.'
    : settled
    ? 'This draft already has a retained receipt. Read the object again before preparing a new action.'
    : canSend
      ? restored
        ? 'Your saved draft is restored with the same intent. Sending it recovers its receipt or submits that exact action.'
        : 'This draft is tied to the object you just read. Send it when you’re ready.'
    : state.world.mode === 'read-only'
      ? 'This world is read-only. You can copy the proposal and inspect its exact details.'
      : 'This proposal cannot be sent here. You can copy it and inspect its exact details.';
  const url = new URL(location.href);
  url.searchParams.delete('preparation');
  url.searchParams.set('draft', draft.draft);
  writeLocation(url);
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
      renderCreatedChildren(result.children || result.allocated || []);
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
  if (state.card) openObject(state.card.object, false, state.card.panel || 'main');
});
$('dismiss-draft').addEventListener('click', clearDraft);
$('copy-preview').addEventListener('click', () => {
  if (!state.draft) return;
  const lines = ['Unsent action preview', state.draft.summary, `Object: ${state.draft.object}`,
    ...Object.entries(state.draft.fields || {}).map(([key, value]) => `${key}: ${text(value)}`),
    'This summary is not an executable town reply.'];
  copy(lines.join('\n'), $('copy-preview'));
});
$('copy-draft').addEventListener('click', () => copy($('draft-command').textContent, $('copy-draft')));
$('copy-wire').addEventListener('click', () => copy($('draft-wire').textContent, $('copy-wire')));
$('download-wire').addEventListener('click', () => {
  const url = URL.createObjectURL(new Blob([$('draft-wire').textContent], { type: 'application/json;charset=utf-8' }));
  const link = element('a');
  link.href = url;
  link.download = 'delvetalk-proposal.json';
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('copy-repository').addEventListener('click', () => copy($('repository-json').textContent, $('copy-repository')));
$('prepare-repository').addEventListener('click', () => {
  const draft = state.draft;
  if (!draft) return;
  busy($('prepare-repository'), 'Preparing record…', async () => {
    const record = await api('/api/repository/prepare', { draft: draft.draft });
    if (state.draft !== draft) return;
    if (typeof record.recordJson !== 'string') throw new Error('The portal did not return an exact repository record.');
    $('repository-json').textContent = record.recordJson;
    $('repository-status').textContent = 'Record prepared. Nothing has been published, authenticated or sent.';
    $('repository-record').hidden = false;
  });
});
$('copy-detail').addEventListener('click', () => copy($('detail-content').textContent, $('copy-detail')));
$('copy-reference').addEventListener('click', () => {
  if (state.card?.objectRef) copy(JSON.stringify(state.card.objectRef), $('copy-reference'));
});
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
function renderViewChildren(card) {
  const target = $('view-children');
  target.replaceChildren();
  const children = card.children || [];
  target.hidden = children.length === 0;
  if (!children.length) return;
  target.append(element('h3', '', 'Look around'));
  target.append(element('p', 'help', 'These are places to read, not actions. Opening one reads its current state separately from this catalogue.'));
  const links = element('div', 'child-links');
  for (const child of children) {
    const button = element('button', 'secondary', child.label);
    button.type = 'button';
    button.addEventListener('click', () => openObject(child.object, true, child.panel, 'push',
      { card: card.card, key: child.key, label: child.label }));
    links.append(button);
  }
  target.append(links);
}
function renderCreatedChildren(children) {
  const target = $('object-children');
  target.replaceChildren();
  const valid = children.filter(child => child && typeof child.object === 'string');
  target.hidden = valid.length === 0;
  if (valid.length) target.append(element('p', 'help', 'Created in this committed action:'));
  for (const child of valid) {
    const button = element('button', 'secondary', child.title || child.object);
    button.type = 'button';
    button.addEventListener('click', () => openObject(child.object, true));
    target.append(button);
  }
}
function configureAuthoring(config) {
  const enabled = Boolean(config) && state.world.mode !== 'public-preview' && state.world.capabilities?.authoring !== false;
  $('source-desk').hidden = !enabled;
  if (!enabled) return;
  const current = $('source-syntax').value;
  $('source-syntax').replaceChildren();
  for (const syntax of config.syntaxes || []) {
    const option = element('option', '', syntax);
    option.value = syntax;
    $('source-syntax').append(option);
  }
  if ([...$('source-syntax').options].some(option => option.value === current)) $('source-syntax').value = current;
  if (!$('source-candidate').value && config.candidates?.length === 1) $('source-candidate').value = config.candidates[0];
  for (const [id, names] of [['candidate-objects', config.candidates || []], ['target-objects', (state.world.objects || []).map(object => object.id)]]) {
    $(id).replaceChildren();
    for (const name of names) {
      const option = element('option');
      option.value = name;
      $(id).append(option);
    }
  }
  if (!$('source-migration').value) $('source-migration').value = '{}';
}
function authoringUrl(id) {
  const url = new URL(location.href);
  if (id) url.searchParams.set('work', id);
  else url.searchParams.delete('work');
  writeLocation(url);
}
function clearAuthoring() {
  if (authoring.pending) return;
  authoring.draft = null;
  authoring.status = null;
  authoring.uncertain = false;
  $('authoring-work').hidden = true;
  authoringUrl(null);
}
async function retainSourceText(value, kind = 'source') {
  const limit = kind === 'scenarios' ? 1048576 : state.world.authoring?.maxSourceBytes || 524288;
  if (new TextEncoder().encode(value).length > limit) throw new Error(`The source limit is ${limit.toLocaleString()} UTF-8 bytes.`);
  return api('/api/authoring/source', { text: value, kind });
}
function exactSourceText(id) {
  const retained = authoring.rawFiles[id];
  return retained?.display === $(id).value ? retained.exact : $(id).value;
}
async function keepSource() {
  const sourceText = exactSourceText('source-text');
  const saved = await retainSourceText(sourceText);
  authoring.source = saved.source;
  authoring.sourceText = $('source-text').value;
  $('source-reference').value = saved.source;
  $('source-retained').textContent = `Kept · ${saved.bytes.toLocaleString()} bytes · ${saved.source.slice(0, 12)}`;
  return saved.source;
}
function updateAuthoringControls() {
  const draft = authoring.draft;
  if (!draft) return;
  const settled = draft.outcome === 'committed' || draft.outcome === 'refused' || Boolean(authoring.status?.job);
  $('send-authoring').disabled = authoring.pending || settled || !draft.canExecute || state.world.mode !== 'local-interactive';
  $('send-authoring').textContent = authoring.status?.job ? 'Job retained' : settled ? 'Outcome retained' : authoring.uncertain ? 'Send / retry saved proposal' : 'Send proposal';
  $('dismiss-authoring').disabled = authoring.pending;
  const phase = authoring.status?.phase;
  $('run-authoring').hidden = draft.operation !== 'compile' || !['queued', 'running'].includes(phase);
  $('run-authoring').disabled = authoring.pending || state.world.mode !== 'local-interactive';
  $('refresh-authoring').disabled = authoring.pending;
}
function showAuthoringDraft(draft, restored = false) {
  authoring.draft = draft;
  authoring.status = null;
  authoring.uncertain = restored && !draft.outcome;
  $('authoring-summary').textContent = text(draft.summary);
  $('authoring-title').textContent = `${draft.operation[0].toUpperCase() + draft.operation.slice(1)} proposal`;
  $('authoring-alias').textContent = `work ${draft.draft.slice(0, 12)}`;
  $('authoring-exact').textContent = draft.wireJson || draft.requestJson || JSON.stringify(draft, null, 2);
  $('authoring-status-exact').hidden = true;
  $('authoring-diagnostics').hidden = true;
  $('authoring-status').textContent = draft.outcome
    ? `Retained outcome: ${draft.outcome}.`
    : restored ? 'Saved proposal restored with its original intent. Check status or send the same proposal to recover its receipt.'
      : state.world.mode === 'read-only' ? 'Prepared for review. Sending and compilation require a configured local session.'
        : 'Prepared only. Review the exact proposal before sending.';
  $('source-candidate').value = draft.candidate || $('source-candidate').value;
  if (draft.target) $('source-target').value = draft.target;
  $('source-desk').open = true;
  $('authoring-work').hidden = false;
  authoringUrl(draft.draft);
  updateAuthoringControls();
}
async function prepareAuthoring(operation) {
  if (authoring.pending || authoring.preparing || authoring.uncertain) throw new Error('Resolve or dismiss the saved source desk proposal before preparing another.');
  authoring.preparing = true;
  try {
    const candidate = $('source-candidate').value.trim();
    if (!candidate) throw new Error('Choose a candidate object.');
    const payload = { operation, candidate };
    if (operation !== 'compile') {
      payload.target = $('source-target').value.trim();
      if (!payload.target) throw new Error('Choose a target object.');
    }
    if (operation === 'submit') {
      payload.syntax = $('source-syntax').value;
      if (!payload.syntax) throw new Error('Choose a syntax.');
      payload.source = authoring.sourceText === $('source-text').value && authoring.source ? authoring.source : await keepSource();
      if (!$('source-scenarios').value.trim()) throw new Error('Supply the scenario JSON for this candidate.');
    payload.scenarios = (await retainSourceText(exactSourceText('source-scenarios'), 'scenarios')).source;
      payload.migrationJson = $('source-migration').value;
    }
    const draft = await api('/api/authoring/prepare', payload);
    showAuthoringDraft(draft);
  } finally { authoring.preparing = false; }
}
async function checkAuthoringStatus() {
  const draft = authoring.draft;
  if (!draft) return;
  const status = await api(`/api/authoring/status?draft=${encodeURIComponent(draft.draft)}`);
  if (authoring.draft !== draft) return;
  authoring.status = status;
  if (status.job) authoring.uncertain = false;
  if (status.receipt?.kind === 'committed' || status.receipt?.kind === 'refused') {
    draft.outcome = status.receipt.kind;
    authoring.uncertain = false;
  }
  const phaseLabels = { prepared: 'Proposal prepared', queued: 'Compile job queued', running: 'Compile job in progress', finished: draft.operation === 'compile' ? 'Compile job finished' : 'Proposal processed' };
  $('authoring-status').textContent = `${phaseLabels[status.phase] || text(status.phase)}${draft.outcome ? ` · ${draft.outcome}` : ''}${status.job ? ` · job ${status.job.slice(0, 12)}` : ''}`;
  const notes = [...(status.diagnostics || []), ...(status.errors || [])];
  $('authoring-diagnostics').hidden = notes.length === 0;
  $('authoring-notes').textContent = notes.map(note => typeof note === 'string' ? note : JSON.stringify(note, null, 2)).join('\n\n');
  $('authoring-status-exact').textContent = status.exactJson || JSON.stringify(status, null, 2);
  $('authoring-status-exact').hidden = false;
  updateAuthoringControls();
}
async function authoringAction(operation) {
  const draft = authoring.draft;
  if (!draft || authoring.pending || authoring.preparing || state.world.mode !== 'local-interactive') return;
  authoring.pending = true;
  updateAuthoringControls();
  $('authoring-status').textContent = operation === 'run' ? 'Running the saved compile job…' : 'Sending the saved proposal…';
  try {
    const reply = await api(`/api/authoring/${operation}`, { draft: draft.draft });
    if (authoring.draft !== draft) return;
    if (reply.kind === 'uncertain') authoring.uncertain = true;
    await checkAuthoringStatus();
    if (reply.children) renderCreatedChildren(reply.children);
    try { await loadWorld(); } catch { /* The retained work remains recoverable. */ }
  } catch (error) {
    if (authoring.draft === draft) {
      authoring.uncertain = true;
      $('authoring-status').textContent = `${error.message} Keep this saved proposal; check status or retry it to recover the same intent.`;
    }
  } finally { authoring.pending = false; updateAuthoringControls(); }
}
$('source-form').addEventListener('submit', event => { event.preventDefault(); busy($('prepare-source'), 'Preparing…', () => prepareAuthoring('submit')); });
$('prepare-compile').addEventListener('click', () => busy($('prepare-compile'), 'Preparing…', () => prepareAuthoring('compile')));
$('prepare-adopt').addEventListener('click', () => busy($('prepare-adopt'), 'Preparing…', () => prepareAuthoring('adopt')));
$('retain-source').addEventListener('click', () => busy($('retain-source'), 'Keeping…', keepSource));
$('load-source').addEventListener('click', () => busy($('load-source'), 'Opening…', async () => {
  const source = $('source-reference').value.trim();
  const saved = await api(`/api/authoring/source?source=${encodeURIComponent(source)}`);
  $('source-text').value = saved.text;
  authoring.rawFiles['source-text'] = { display: $('source-text').value, exact: saved.text };
  authoring.source = saved.source || source;
  authoring.sourceText = $('source-text').value;
  $('source-retained').textContent = `Opened retained source · ${source.slice(0, 12)}`;
}));
for (const [fileId, textId] of [['source-file', 'source-text'], ['scenario-file', 'source-scenarios']]) {
  $(fileId).addEventListener('change', async () => {
    const file = $(fileId).files[0];
    if (!file) return;
    try {
      const limit = fileId === 'scenario-file' ? 1048576 : state.world.authoring?.maxSourceBytes || 524288;
      if (file.size > limit) throw new Error('This file exceeds the source size limit.');
      const exact = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer());
      $(textId).value = exact;
      authoring.rawFiles[textId] = { exact, display: $(textId).value };
      if (fileId === 'source-file') $('source-retained').textContent = 'File opened locally. Keep source to retain it.';
    } catch (error) { notice(error.message, true); }
  });
}
$('source-text').addEventListener('input', () => { $('source-retained').textContent = 'Edited · not yet retained'; });
$('dismiss-authoring').addEventListener('click', clearAuthoring);
$('copy-authoring').addEventListener('click', () => copy($('authoring-exact').textContent, $('copy-authoring')));
$('send-authoring').addEventListener('click', () => authoringAction('execute'));
$('run-authoring').addEventListener('click', () => authoringAction('run'));
$('refresh-authoring').addEventListener('click', () => busy($('refresh-authoring'), 'Checking…', checkAuthoringStatus));
async function openLocation() {
  try {
    if (state.sending || authoring.pending) {
      writeLocation(state.location);
      return notice('Wait for the send result before navigating.');
    }
    const routeGeneration = ++state.routeGeneration;
    const requestedParams = new URL(location.href).searchParams;
    const requested = requestedParams.get('object');
    const savedDraftId = requestedParams.get('draft');
    const preparationId = requestedParams.get('preparation');
    const preparationGeneration = state.preparationGeneration;
    const workId = requestedParams.get('work');
    if (authoring.uncertain && authoring.draft && workId !== authoring.draft.draft) {
      const url = new URL(location.href);
      url.searchParams.set('work', authoring.draft.draft);
      writeLocation(url);
    }
    const world = state.world;
    let savedDraft = state.uncertain ? state.draft : null;
    let draftError = null;
    let savedPreparation = null;
    let preparationError = null;
    if (savedDraftId && !state.uncertain) {
      try { savedDraft = await api(`/api/draft?draft=${encodeURIComponent(savedDraftId)}`); }
      catch (error) { draftError = error; }
    }
    if (preparationId && !savedDraftId && !state.uncertain) {
      try { savedPreparation = await api(`/api/preparation?preparation=${encodeURIComponent(preparationId)}`); }
      catch (error) { preparationError = error; }
    }
    if (routeGeneration !== state.routeGeneration) return;
    if (savedPreparation && (preparationGeneration !== state.preparationGeneration || state.sending || state.uncertain
        || authoring.pending || authoring.preparing || authoring.uncertain)) {
      if (state.uncertain && state.draft) {
        const kept = new URL(state.location);
        kept.searchParams.set('draft', state.draft.draft);
        kept.searchParams.delete('preparation');
        writeLocation(kept);
      } else if (state.sending || authoring.pending || authoring.preparing || authoring.uncertain) writeLocation(state.location);
      return;
    }
    const id = savedPreparation?.object || (world.objects || []).find(object => object.id === requested)?.id
      || savedDraft?.object || world.defaultObject || world.objects?.[0]?.id;
    const panel = requestedParams.get('panel') || (savedDraft?.object === id ? savedDraft.panel : null) || 'main';
    if (id && !await openObject(id, false, panel, 'replace', null, savedPreparation?.card)) return;
    if (savedDraft) showDraft(savedDraft, true);
    else if (draftError) notice(`The saved draft could not be opened: ${draftError.message}`, true);
    else if (savedPreparation && preparationGeneration === state.preparationGeneration && !state.sending && !state.uncertain
        && !authoring.pending && !authoring.preparing && !authoring.uncertain) showPreparation(savedPreparation);
    else if (preparationError) notice(`The saved preparation could not be opened: ${preparationError.message}`, true);
    if (workId && !authoring.uncertain && world.authoring && world.capabilities?.authoring !== false) {
      // openObject advances the route generation. Capture its winning route,
      // then recheck after loading: a newer route or local work may now own the UI.
      const winningRoute = state.routeGeneration;
      const previousWork = authoring.draft;
      let restoredWork;
      const mayRestore = () => winningRoute === state.routeGeneration && !state.sending
        && !authoring.pending && !authoring.preparing && !authoring.uncertain
        && authoring.draft === previousWork;
      try {
        restoredWork = await api(`/api/authoring/draft?draft=${encodeURIComponent(workId)}`);
        if (!mayRestore()) return;
        showAuthoringDraft(restoredWork, true);
        await checkAuthoringStatus();
      } catch (error) {
        if (mayRestore() || (winningRoute === state.routeGeneration
            && authoring.draft === restoredWork && !authoring.pending))
          notice(`The saved source desk proposal could not be opened: ${error.message}`, true);
      }
    }
  } catch (error) { notice(error.message, true); }
}
window.addEventListener('popstate', openLocation);
(async () => {
  try { await loadWorld(); await openLocation(); }
  catch (error) { notice(error.message, true); $('mode').textContent = 'World unavailable'; }
})();
