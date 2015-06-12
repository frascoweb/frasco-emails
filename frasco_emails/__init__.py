from frasco import Feature, action, current_context, OptionMissingError, copy_extra_feature_options, current_app
from jinja_macro_tags import MacroLoader, MacroRegistry
from frasco.utils import parse_yaml_frontmatter
from frasco.expression import compile_expr, eval_expr
from flask_mail import Mail, Message, email_dispatched, Attachment, force_text
from jinja2 import ChoiceLoader, FileSystemLoader, PackageLoader, TemplateNotFound
from contextlib import contextmanager
import html2text
import premailer
import os
import datetime
import re
import markdown



_url_regexp = re.compile(r'(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+)')
def clickable_links(text):
    return _url_regexp.sub(r'<a href="\1">\1</a>', text)


class EmailsFeature(Feature):
    """Send emails using SMTP
    """
    name = "emails"
    defaults = {"default_layout": "layout.html",
                "default_template_vars": {},
                "inline_css": False,
                "auto_render_missing_content_type": True,
                "log_messages": None, # default is app.testing
                "dump_logged_messages": True,
                "dumped_messages_folder": "email_logs",
                "localized_emails": None,
                "default_locale": None,
                "markdown_options": {},
                "silent_failures": False}

    def init_app(self, app):
        copy_extra_feature_options(self, app.config, "MAIL_")

        self.client = Mail(app)
        self.connection = None

        self.templates_loader = [FileSystemLoader(os.path.join(app.root_path, "emails"))]
        layout_loader = PackageLoader(__name__, "templates")
        loader = ChoiceLoader([ChoiceLoader(self.templates_loader), layout_loader])
        self.jinja_env = app.jinja_env.overlay(loader=MacroLoader(loader))
        self.jinja_env.macros = MacroRegistry(self.jinja_env) # the overlay methods does not call the constructor of extensions
        self.jinja_env.macros.register_from_template("layouts/macros.html")
        self.jinja_env.default_layout = self.options["default_layout"]
        self.jinja_env.filters['clickable_links'] = clickable_links

        if (self.options["log_messages"] is not None and self.options["log_messages"]) or \
            (self.options["log_messages"] is None and app.testing):
            email_dispatched.connect(self.log_message)

        self.locale = None
        if app.features.exists('babel'):
            if self.options['default_locale'] is None:
                self.options['default_locale'] = app.config['BABEL_DEFAULT_LOCALE']
            if self.options['localized_emails'] is None:
                self.options['localized_emails'] = '{locale}/{filename}'

    def add_template_folder(self, path):
        self.templates_loader.append(FileSystemLoader(path))

    def add_templates_from_package(self, pkg_name, pkg_path="emails"):
        self.templates_loader.append(PackageLoader(pkg_name, pkg_path))

    def render_message(self, template_filename, auto_render_missing_content_type=None,\
                       auto_html_layout="layouts/text.html", auto_markdown_template="layouts/markdown.html", **vars):
        text_body = None
        html_body = None
        vars = dict(self.options["default_template_vars"], **vars)
        filename, ext = os.path.splitext(template_filename)

        localized_filename = None
        if self.options['localized_emails']:
            locale = vars.get('locale', self.locale)
            if locale is None and 'current_locale' in current_context:
                locale = current_context['current_locale']
            if locale and locale != self.options['default_locale']:
                localized_filename = self.options['localized_emails'].format(**{
                    "locale": locale, "filename": template_filename,
                    "name": filename, "ext": ext})

        source = None
        for tpl_filename in [localized_filename, template_filename]:
            if not tpl_filename:
                continue
            # only extract the frontmatter from the first template if
            # multiple extensions are provided
            filename, ext = os.path.splitext(tpl_filename)
            if "," in ext:
                tpl_filename = filename + ext.split(",")[0]
            try:
                source, _, __ = self.jinja_env.loader.get_source(self.jinja_env, tpl_filename)
            except TemplateNotFound:
                pass
            if source:
                break
        if source is None:
            raise TemplateNotFound(template_filename)

        frontmatter, source = parse_yaml_frontmatter(source)
        if frontmatter:
            frontmatter = eval_expr(compile_expr(frontmatter), vars)
            vars = dict(frontmatter, **vars)

        templates = [("%s.%s" % (filename, e), e) for e in ext[1:].split(",")]
        for tpl_filename, ext in templates:
            rendered = self.jinja_env.get_template(tpl_filename).render(**vars)
            if ext == "html":
                html_body = rendered
            elif ext == "txt":
                text_body = rendered
            elif ext == "md":
                text_body = rendered
                content = markdown.markdown(rendered, **self.options["markdown_options"])
                html_body = self.jinja_env.get_template(auto_markdown_template).render(
                    content=content, **vars)

        if (auto_render_missing_content_type is not None and auto_render_missing_content_type) or \
          (auto_render_missing_content_type is None and self.options["auto_render_missing_content_type"]):
            if html_body is None:
                html_body = self.jinja_env.get_template(auto_html_layout).render(
                    text_body=text_body, **vars)
            if text_body is None:
                text_body = html2text.html2text(html_body)

        if html_body and self.options["inline_css"]:
            html_body = premailer.transform(html_body)

        return (frontmatter, text_body, html_body)

    @action("create_email_message", as_="email_message")
    def create_message(self, to, tpl, **vars):
        recipients = to if isinstance(to, (list, tuple)) else [to]
        frontmatter, text_body, html_body = self.render_message(tpl, **vars)

        kwargs = {}
        for k in ('subject', 'sender', 'cc', 'bcc', 'attachments', 'reply_to', 'send_date', 'charset', 'extra_headers'):
            if k in vars:
                kwargs[k] = vars[k]
            elif frontmatter and k in frontmatter:
                kwargs[k] = frontmatter[k]
        kwargs["date"] = kwargs.pop("send_date", None)

        if not kwargs.get("subject"):
            raise OptionMissingError("Missing subject for email with template '%s'" % tpl)
        subject = kwargs.pop("subject")
        attachments = kwargs.pop("attachments", None)

        msg = Message(recipients=recipients, subject=subject, body=text_body, html=html_body, **kwargs)
        msg.template = tpl

        if attachments:
            for attachment in attachments:
                if isinstance(attachment, Attachment):
                    msg.attachments.append(attachment)
                elif isinstance(attachment, dict):
                    msg.attach(**attachment)
                else:
                    msg.attach(attachment)

        current_context.data.mail_message = msg
        return msg

    @action("add_email_attachment", default_option="filename")
    def add_attachment(self, filename, msg=None, **kwargs):
        msg = msg or current_context.data.mail_message
        msg.attach(filename, **kwargs)

    @action("start_bulk_emails")
    def start_bulk(self):
        try:
            self.connection = self.client.connect()
        except Exception as e:
            if not self.options['silent_failures']:
                raise e
            current_app.logger.error(e)
        # simulate entering a with context
        # (flask-mail does not provide a way to connect otherwise)
        self.connection.__enter__()

    @action("stop_bulk_emails")
    def stop_bulk(self):
        self.connection.__exit__(None, None, None) # see start_bulk()
        self.connection = None

    @contextmanager
    def bulk(self):
        self.start_bulk()
        try:
            yield self
        finally:
            self.stop_bulk()

    @action("send_email")
    def send(self, to=None, tpl=None, **kwargs):
        msg = None
        if isinstance(to, Message):
            msg = to
        elif to is None and "mail_message" in current_context.data:
            msg = current_context.data.mail_message
        else:
            if not to:
                raise OptionMissingError("A recipient must be provided when sending an email")
            if not tpl:
                raise OptionMissingError("A template must be provided when sending an email")
            msg = self.create_message(to, tpl, **kwargs)

        try:
            if self.connection:
                self.connection.send(msg)
            else:
                self.client.send(msg)
        except Exception as e:
            if not self.options['silent_failures']:
                raise e
            current_app.logger.error(e)

    def log_message(self, message, app):
        app.logger.debug("Email %s sent to %s as \"%s\"" % (message.template, message.recipients, message.subject))
        if self.options["dump_logged_messages"]:
            path = os.path.join(app.root_path, self.options["dumped_messages_folder"])
            if not os.path.exists(path):
                os.mkdir(path, 0777)
            filename = os.path.join(path, "-".join([
                datetime.datetime.now().isoformat("-"),
                os.path.splitext(message.template)[0].replace("/", "_"),
                "-".join(message.recipients)]))
            if message.body:
                with open(filename + ".txt", "w") as f:
                    f.write(message.body.encode('utf-8'))
            if message.html:
                with open(filename + ".html", "w") as f:
                    f.write(message.html.encode('utf-8'))