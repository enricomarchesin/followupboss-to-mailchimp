# FollowUpBoss to Mailchimp

Sync all email address from FollowUpBoss to Mailchimp, including addresses of secondary contacts.

## Configure

To use this tool, you need to make the API keys for both FollowUpBoss and Mailchimp available to it.

The simplest way is to create a file called `.env` with the two keys in it:

```env
FOLLOWUPBOSS_API_KEY=fka_0zfv********
MAILCHIMP_API_KEY=61802e********-us5
```

Note the last 3 letters at the end of the Mailchimp key, `us5` in the example above. If yours are different, make sure to update also the API URL in the `settings.yaml` file.

For example, if they are dc1, update this line in `settings.yaml`:

```yml
  mailchimp_api_url: "https://us5.api.mailchimp.com/3.0"
```

so that it reads instead:

```yml
  mailchimp_api_url: "https://dc1.api.mailchimp.com/3.0"
```

## Usage

The easiest way to use the tool is using Docker Compose. You can install it following the instructions at:

> https://docs.docker.com/compose/install/

### Windows

```bat
start.bat
```

### MacOS and Linux

```bat
./start.sh
```
