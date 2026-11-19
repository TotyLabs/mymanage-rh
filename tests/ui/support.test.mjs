import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

const source = await readFile(new URL('../../ui/pages/soporte.js', import.meta.url), 'utf8');
const supportPage = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);

function createForm(reasonValue) {
  const reason = {
    value: reasonValue,
    attributes: {},
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
  };
  const fields = [
    { value: 'Convenio de prueba', required: false },
    { value: '1 a 10 empleados', required: false },
    { value: 'Plataforma', required: false },
  ];
  const serviceFields = {
    hidden: true,
    querySelectorAll() {
      return fields;
    },
  };
  const subjectInput = {
    value: 'Consulta sobre recibos',
    required: true,
    dataset: {},
  };
  const subjectField = { hidden: false };

  return {
    fields,
    reason,
    serviceFields,
    subjectField,
    subjectInput,
    querySelector(selector) {
      if (selector === '#supportReason') return reason;
      if (selector === '#supportServiceFields') return serviceFields;
      if (selector === '#supportSubjectField') return subjectField;
      if (selector === '#supportSubject') return subjectInput;
      return null;
    },
  };
}

test('service request fields are required only for service inquiries and cleared otherwise', () => {
  const form = createForm('');

  supportPage.updateServiceRequestFields(form);
  assert.equal(form.serviceFields.hidden, true);
  assert.equal(form.reason.attributes['aria-expanded'], 'false');
  assert.ok(form.fields.every((field) => !field.required));
  assert.equal(form.subjectField.hidden, false);
  assert.equal(form.subjectInput.required, true);

  form.reason.value = 'service';
  supportPage.updateServiceRequestFields(form);
  assert.equal(form.serviceFields.hidden, false);
  assert.equal(form.reason.attributes['aria-expanded'], 'true');
  assert.ok(form.fields.every((field) => field.required));
  assert.equal(form.subjectField.hidden, true);
  assert.equal(form.subjectInput.required, false);
  assert.equal(form.subjectInput.value, 'Solicitud de servicio');

  form.reason.value = 'support';
  supportPage.updateServiceRequestFields(form);
  assert.equal(form.serviceFields.hidden, true);
  assert.equal(form.reason.attributes['aria-expanded'], 'false');
  assert.ok(form.fields.every((field) => !field.required && field.value === ''));
  assert.equal(form.subjectField.hidden, false);
  assert.equal(form.subjectInput.required, true);
  assert.equal(form.subjectInput.value, 'Consulta sobre recibos');
});
