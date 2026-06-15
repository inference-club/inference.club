from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inference", "0028_mediaasset_provenance"),
    ]

    operations = [
        migrations.AlterField(
            model_name="inferencerequest",
            name="inference_type",
            field=models.CharField(
                choices=[
                    ("LLM", "Language Model"),
                    ("STT", "Speech to Text"),
                    ("IMAGE", "Image Generation"),
                    ("VIDEO", "Video Generation"),
                    ("TTS", "Text to Speech"),
                    ("MESH", "Image to 3D"),
                    ("MUSIC", "Music Generation"),
                    ("VOICE", "Voice Cloning"),
                    ("SCRAPE", "Web Scrape"),
                    ("RENDER", "Video Compose"),
                    ("ENHANCE", "Audio Enhancement"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="providerservice",
            name="service_type",
            field=models.CharField(
                choices=[
                    ("llm", "Language model"),
                    ("stt", "Speech to text"),
                    ("tts", "Text to speech"),
                    ("image", "Image generation"),
                    ("mesh", "Image to 3D"),
                    ("music", "Music generation"),
                    ("video", "Video generation"),
                    ("scrape", "Web scrape"),
                    ("render", "Video compose"),
                    ("audio-enhance", "Audio enhancement"),
                ],
                default="llm",
                max_length=16,
            ),
        ),
    ]
