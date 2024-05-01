import lib.clients.web_api.base


class WebAPIProvisioningClient(lib.clients.web_api.base.WebAPIBaseClient):

  async def get_challenge(self):
    return await self.get(path="/provisioning/challenge")

  async def post_register_app(
      self,
      mobile_device_id: str,
      mobile_device_model: str,
  ):
    """Post to the /provisioning/register_app endpoint.

    Args:
      mobile_device_id: The ID of the mobile device to register.
      mobile_device_model: The model of the mobile device to register.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {
          "device_id": <The ID of the device>,
          "pkcs12_certificate": <The registered certificate>,
        }
    """
    data = {
        "mobile_device_id": mobile_device_id,
        "mobile_device_model": mobile_device_model
    }
    return await self.post(
        path="/provisioning/register_app",
        data=data,
    )

  async def get_virtual_control_self_bootstrap(
      self,
      home_property_id: str,
      token: str,
  ):
    """Post to the /provisioning/virtual-control-self-bootstrap endpoint.

    Args:
      home_property_id: The property ID of the home we are adding the virtual control to.
      token: A JWT to be used for the '/provisioning/virtual-control-self-bootstrap' endpoint.

    Returns:
      A lib.clients.web_api.client.WebAPIResponse with a JSON body containing:
        {
          "device_id": <The ID of the device>,
          "pkcs12_certificate": <The registered certificate>,
          "bootstrap": <The serialized BootstrapParameters>,
        }
    """
    params = {
        "home_property_id": home_property_id,
    }
    return await self.get(
        path="/provisioning/virtual-control-self-bootstrap",
        params=params,
        extra_headers={"Authorization": f"Bearer {token}"}
    )
